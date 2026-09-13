#include "sensor_runtime.h"
#include "sensor_protocol.h"
#include "gesture_sensor.h"
#include "control_frame.h"
#include "device_ack.h"
#include "driver/i2c_master.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"

namespace kadence_sensors {
namespace {
constexpr int TimeoutMs = 10;
constexpr uint8_t HubAddress = CONFIG_KADENCE_SENSOR_HUB_ADDRESS;
portMUX_TYPE snapshot_lock = portMUX_INITIALIZER_UNLOCKED;
Snapshot published;
GestureSnapshot gesture_published;

class ExternalBus final : public Bus {
public:
    bool initialize() {
        i2c_master_bus_config_t config{};
        config.i2c_port = I2C_NUM_0;
        config.sda_io_num = GPIO_NUM_2;
        config.scl_io_num = GPIO_NUM_1;
        config.clk_source = I2C_CLK_SRC_DEFAULT;
        config.glitch_ignore_cnt = 7;
        config.flags.enable_internal_pullup = true;
        // Never take over an existing controller or touch the internal I2C1.
        if (i2c_new_master_bus(&config, &bus_) != ESP_OK) return false;
        i2c_device_config_t device{};
        device.dev_addr_length = I2C_ADDR_BIT_LEN_7;
        device.device_address = HubAddress;
        device.scl_speed_hz = 100000;
        if (i2c_master_bus_add_device(bus_, &device, &hub_) == ESP_OK) {
            device.device_address = 0x73;
            if (i2c_master_bus_add_device(bus_, &device, &gesture_) == ESP_OK) return true;
            i2c_master_bus_rm_device(hub_);
        }
        i2c_del_master_bus(bus_);
        bus_ = nullptr;
        return false;
    }
    Result probe(uint8_t address) override {
        const auto err = i2c_master_probe(bus_, address, TimeoutMs);
        return err == ESP_OK ? Result::Ack : err == ESP_ERR_NOT_FOUND ? Result::Nack : Result::Error;
    }
    bool write_switch(uint8_t address, uint8_t mask) override {
        return address == HubAddress && i2c_master_transmit(hub_, &mask, 1, TimeoutMs) == ESP_OK;
    }
    bool read_switch(uint8_t address, uint8_t& mask) override {
        return address == HubAddress && i2c_master_receive(hub_, &mask, 1, TimeoutMs) == ESP_OK;
    }
    bool register_io(uint8_t address, uint8_t reg, uint8_t* data, size_t size, bool read) override {
        if (address != 0x73 || !size || size > 2) return false;
        if (read) return i2c_master_transmit_receive(gesture_, &reg, 1, data, size, TimeoutMs) == ESP_OK;
        uint8_t bytes[3]{reg, data[0], static_cast<uint8_t>(size > 1 ? data[1] : 0)};
        return i2c_master_transmit(gesture_, bytes, size + 1, TimeoutMs) == ESP_OK;
    }
private:
    i2c_master_dev_handle_t gesture_ = nullptr;
    i2c_master_bus_handle_t bus_ = nullptr;
    i2c_master_dev_handle_t hub_ = nullptr;
};

void publish(const Snapshot& value) {
    portENTER_CRITICAL(&snapshot_lock);
    published = value;
    portEXIT_CRITICAL(&snapshot_lock);
}
void unavailable() {
    Snapshot value;
    value.hub_address = HubAddress;
    value.hub = Health::Unavailable;
    value.sampled_ms = static_cast<uint32_t>(esp_timer_get_time() / 1000);
    publish(value);
}
void worker(void*) {
    ExternalBus bus;
    if (!bus.initialize()) {
        unavailable();
        ESP_LOGW("SENSORS", "state=unavailable stage=external-bus");
        vTaskDelete(nullptr);
        return;
    }
    Discovery discovery(bus, HubAddress);
    GestureSensor gesture(bus, HubAddress);
    bool register_turn = false;
    Health last = Health::Starting;
    while (true) {
        const auto now = static_cast<uint64_t>(esp_timer_get_time()) / 1000;
        register_turn = !register_turn;
        if (!register_turn && discovery.step(now)) {
            const auto& snapshot = discovery.snapshot();
            publish(snapshot);
            // No telemetry firehose on the serial control link.
            if (snapshot.hub != last) {
                ESP_LOGI("SENSORS", "hub=%s address=0x%02x bus=external", health_name(snapshot.hub), HubAddress);
                last = snapshot.hub;
            }
        }
        // Discovery and register traffic share this worker; never interleave selections.
        if (register_turn && discovery.idle()) {
            const auto result = gesture.step(now, discovery.snapshot());
            if (result.failed) {
                discovery.measurement_fault(now, result.isolated, 0);
                publish(discovery.snapshot());
            }
        }
        portENTER_CRITICAL(&snapshot_lock);
        gesture_published = gesture.snapshot();
        portEXIT_CRITICAL(&snapshot_lock);
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}
}

void start() {
    Snapshot initial;
    initial.hub_address = HubAddress;
    publish(initial);
    if (xTaskCreate(worker, "kade-sensors", 4096, nullptr, 1, nullptr) != pdPASS) {
        unavailable();
        ESP_LOGW("SENSORS", "state=unavailable stage=worker");
    }
}

bool route(const char* raw, void (*emit)(const char*)) {
    cJSON* root = cJSON_Parse(raw);
    const auto request = parse_request(root);
    if (request == Request::Status || request == Request::Gesture) {
        Snapshot snapshot;
        GestureSnapshot gesture;
        portENTER_CRITICAL(&snapshot_lock);
        snapshot = published;
        gesture = gesture_published;
        portEXIT_CRITICAL(&snapshot_lock);
        char ack[kadence_control::FrameBytes]{};
        const auto* id = cJSON_GetObjectItemCaseSensitive(root, "id");
        const auto now = static_cast<uint32_t>(esp_timer_get_time() / 1000);
        const bool is_gesture = request == Request::Gesture;
        if (device_ack(id->valuestring, is_gesture ? "sensors.gesture" : "sensors.status",
                       is_gesture ? gesture_payload(gesture, now) : status_payload(snapshot, now), ack, sizeof(ack)) && emit)
            emit(ack);
    }
    cJSON_Delete(root);
    return request != Request::Other;
}
}
