#include "unitv2_uart.h"

#include <cstdint>
#include <cstdio>
#include <cstring>

#include "cJSON.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace kadence_unitv2 {
namespace {

constexpr const char* kLogTag = "UNITV2";
constexpr uart_port_t kUart = UART_NUM_2;
constexpr int kBaud = 115200;
constexpr gpio_num_t kTx = GPIO_NUM_17;
constexpr gpio_num_t kRx = GPIO_NUM_18;
constexpr size_t kLineBytes = 1024;
constexpr uint32_t kWorkerStackBytes = 6144;

struct Snapshot {
    bool uart_ready = false;
    bool command_sent = false;
    uint32_t valid_json = 0;
    uint32_t parse_errors = 0;
    uint32_t bytes_rx = 0;
    uint32_t last_json_ms = 0;
    char running[48]{};
    char msg[64]{};
};

portMUX_TYPE g_lock = portMUX_INITIALIZER_UNLOCKED;
Snapshot g_snapshot;

uint32_t now_ms()
{
    return static_cast<uint32_t>(esp_timer_get_time() / 1000);
}

void copy_string(char* output, size_t output_size, const cJSON* item)
{
    if (output == nullptr || output_size == 0 || !cJSON_IsString(item) ||
        item->valuestring == nullptr) {
        return;
    }
    std::snprintf(output, output_size, "%s", item->valuestring);
}

void publish_valid_json(const cJSON* root, uint32_t received_bytes)
{
    Snapshot next;
    portENTER_CRITICAL(&g_lock);
    next = g_snapshot;
    portEXIT_CRITICAL(&g_lock);

    ++next.valid_json;
    next.bytes_rx += received_bytes;
    next.last_json_ms = now_ms();
    copy_string(next.running, sizeof(next.running),
                cJSON_GetObjectItemCaseSensitive(root, "running"));
    copy_string(next.msg, sizeof(next.msg),
                cJSON_GetObjectItemCaseSensitive(root, "msg"));

    portENTER_CRITICAL(&g_lock);
    g_snapshot = next;
    portEXIT_CRITICAL(&g_lock);

    ESP_LOGI(kLogTag,
             "json=valid count=%u running=%s msg=%s",
             static_cast<unsigned>(next.valid_json),
             next.running[0] ? next.running : "unknown",
             next.msg[0] ? next.msg : "none");
}

void publish_parse_error(uint32_t received_bytes)
{
    portENTER_CRITICAL(&g_lock);
    ++g_snapshot.parse_errors;
    g_snapshot.bytes_rx += received_bytes;
    portEXIT_CRITICAL(&g_lock);
}

void consume_line(char* line, size_t length)
{
    if (line == nullptr || length == 0) return;

    char* json = std::strchr(line, '{');
    if (json == nullptr) {
        publish_parse_error(static_cast<uint32_t>(length));
        return;
    }

    cJSON* root = cJSON_Parse(json);
    if (root == nullptr || !cJSON_IsObject(root)) {
        cJSON_Delete(root);
        publish_parse_error(static_cast<uint32_t>(length));
        return;
    }

    publish_valid_json(root, static_cast<uint32_t>(length));
    cJSON_Delete(root);
}

void worker(void*)
{
    char line[kLineBytes]{};
    size_t used = 0;

    while (true) {
        uint8_t byte = 0;
        const int count = uart_read_bytes(kUart, &byte, 1, pdMS_TO_TICKS(20));
        if (count <= 0) continue;

        if (byte == '\r' || byte == '\n') {
            if (used > 0) {
                line[used] = '\0';
                consume_line(line, used);
                used = 0;
            }
            continue;
        }

        if (used + 1 < sizeof(line)) {
            line[used++] = static_cast<char>(byte);
        } else {
            publish_parse_error(static_cast<uint32_t>(used));
            used = 0;
        }
    }
}

bool emit_status(const char* request_id, void (*emit)(const char*))
{
    if (request_id == nullptr || request_id[0] == '\0' || emit == nullptr) return false;

    Snapshot snapshot;
    portENTER_CRITICAL(&g_lock);
    snapshot = g_snapshot;
    portEXIT_CRITICAL(&g_lock);

    cJSON* root = cJSON_CreateObject();
    cJSON* payload = cJSON_CreateObject();
    if (root == nullptr || payload == nullptr) {
        cJSON_Delete(payload);
        cJSON_Delete(root);
        return false;
    }

    const uint32_t age_ms = snapshot.valid_json > 0
        ? static_cast<uint32_t>(now_ms() - snapshot.last_json_ms)
        : 0;

    bool built = true;
    built = built && cJSON_AddNumberToObject(root, "v", 1) != nullptr;
    built = built && cJSON_AddStringToObject(root, "id", request_id) != nullptr;
    built = built && cJSON_AddStringToObject(root, "ts", "device") != nullptr;
    built = built && cJSON_AddStringToObject(root, "kind", "ack") != nullptr;
    built = built && cJSON_AddStringToObject(root, "name", "camera.unitv2.status") != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "ok", snapshot.uart_ready) != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "uart_ready", snapshot.uart_ready) != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "command_sent", snapshot.command_sent) != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "response_seen", snapshot.valid_json > 0) != nullptr;
    built = built && cJSON_AddNumberToObject(payload, "valid_json", snapshot.valid_json) != nullptr;
    built = built && cJSON_AddNumberToObject(payload, "parse_errors", snapshot.parse_errors) != nullptr;
    built = built && cJSON_AddNumberToObject(payload, "bytes_rx", snapshot.bytes_rx) != nullptr;
    built = built && cJSON_AddNumberToObject(payload, "last_response_age_ms", age_ms) != nullptr;
    if (snapshot.running[0]) {
        built = built && cJSON_AddStringToObject(payload, "running", snapshot.running) != nullptr;
    }
    if (snapshot.msg[0]) {
        built = built && cJSON_AddStringToObject(payload, "msg", snapshot.msg) != nullptr;
    }

    if (built) {
        cJSON_AddItemToObject(root, "payload", payload);
        payload = nullptr;
    }

    char* rendered = built ? cJSON_PrintUnformatted(root) : nullptr;
    if (rendered == nullptr) {
        cJSON_free(rendered);
        cJSON_Delete(payload);
        cJSON_Delete(root);
        return false;
    }

    emit(rendered);
    cJSON_free(rendered);
    cJSON_Delete(root);
    return true;
}

}  // namespace

bool start()
{
    uart_config_t config{};
    config.baud_rate = kBaud;
    config.data_bits = UART_DATA_8_BITS;
    config.parity = UART_PARITY_DISABLE;
    config.stop_bits = UART_STOP_BITS_1;
    config.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
    config.rx_flow_ctrl_thresh = 0;
    config.source_clk = UART_SCLK_DEFAULT;

    esp_err_t err = uart_driver_install(kUart, 4096, 1024, 0, nullptr, 0);
    if (err != ESP_OK) {
        ESP_LOGW(kLogTag, "status=unavailable stage=driver-install err=%s", esp_err_to_name(err));
        return false;
    }

    err = uart_param_config(kUart, &config);
    if (err == ESP_OK) {
        err = uart_set_pin(kUart, kTx, kRx, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    }
    if (err != ESP_OK) {
        ESP_LOGW(kLogTag, "status=unavailable stage=config err=%s", esp_err_to_name(err));
        uart_driver_delete(kUart);
        return false;
    }

    uart_flush_input(kUart);

    portENTER_CRITICAL(&g_lock);
    g_snapshot = Snapshot{};
    g_snapshot.uart_ready = true;
    portEXIT_CRITICAL(&g_lock);

    const BaseType_t created =
        xTaskCreate(worker, "unitv2-uart", kWorkerStackBytes, nullptr, 2, nullptr);
    if (created != pdPASS) {
        portENTER_CRITICAL(&g_lock);
        g_snapshot.uart_ready = false;
        portEXIT_CRITICAL(&g_lock);
        uart_driver_delete(kUart);
        ESP_LOGW(kLogTag, "status=unavailable stage=worker");
        return false;
    }

    constexpr char command[] = "{\"function\":\"Camera Stream\",\"args\":\"\"}\r\n";
    const int written = uart_write_bytes(kUart, command, sizeof(command) - 1);
    const bool sent = written == static_cast<int>(sizeof(command) - 1) &&
                      uart_wait_tx_done(kUart, pdMS_TO_TICKS(100)) == ESP_OK;

    portENTER_CRITICAL(&g_lock);
    g_snapshot.command_sent = sent;
    portEXIT_CRITICAL(&g_lock);

    ESP_LOGI(kLogTag,
             "status=ready uart=2 baud=%d tx=%d rx=%d command_sent=%d",
             kBaud,
             static_cast<int>(kTx),
             static_cast<int>(kRx),
             sent ? 1 : 0);
    return true;
}

bool route(const char* raw, void (*emit)(const char*))
{
    if (raw == nullptr) return false;

    cJSON* root = cJSON_Parse(raw);
    if (root == nullptr || !cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return false;
    }

    const cJSON* version = cJSON_GetObjectItemCaseSensitive(root, "v");
    const cJSON* id = cJSON_GetObjectItemCaseSensitive(root, "id");
    const cJSON* kind = cJSON_GetObjectItemCaseSensitive(root, "kind");
    const cJSON* name = cJSON_GetObjectItemCaseSensitive(root, "name");

    const bool handled =
        cJSON_IsNumber(version) && version->valuedouble == 1.0 &&
        cJSON_IsString(id) && id->valuestring != nullptr && id->valuestring[0] != '\0' &&
        cJSON_IsString(kind) && kind->valuestring != nullptr &&
        std::strcmp(kind->valuestring, "command") == 0 &&
        cJSON_IsString(name) && name->valuestring != nullptr &&
        std::strcmp(name->valuestring, "camera.unitv2.status") == 0;

    bool emitted = true;
    if (handled) emitted = emit_status(id->valuestring, emit);
    cJSON_Delete(root);
    return handled && emitted;
}

}  // namespace kadence_unitv2
