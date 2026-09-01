#include "body_contract.h"

#include <array>
#include <cinttypes>
#include <cstdint>
#include <cstdio>

#include "driver/i2c_master.h"
#include "driver/i2s_std.h"
#include "esp_app_desc.h"
#include "esp_codec_dev.h"
#include "esp_codec_dev_defaults.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace {

constexpr const char* kLogTag = "KADE-BODY";
constexpr uint32_t kHeartbeatMs = 5000;
constexpr int kI2cTimeoutMs = 250;
constexpr int kOpenAttempts = 3;
constexpr int kOutputVolume = 65;
constexpr int kToneSamples = 16000;
constexpr int kSilenceSamples = 800;

constexpr gpio_num_t kI2cSda = GPIO_NUM_12;
constexpr gpio_num_t kI2cScl = GPIO_NUM_11;
constexpr uint8_t kAxp2101Address = 0x34;
constexpr uint8_t kAw9523Address = 0x58;

constexpr gpio_num_t kAudioMclk = GPIO_NUM_0;
constexpr gpio_num_t kAudioWs = GPIO_NUM_33;
constexpr gpio_num_t kAudioBclk = GPIO_NUM_34;
constexpr gpio_num_t kAudioDout = GPIO_NUM_13;

struct ProbeHardware {
    i2c_master_bus_handle_t i2c_bus = nullptr;
    i2c_master_dev_handle_t pmic = nullptr;
    i2c_master_dev_handle_t io_expander = nullptr;
};

struct OutputProbe {
    i2s_chan_handle_t tx = nullptr;
    const audio_codec_data_if_t* data_if = nullptr;
    const audio_codec_ctrl_if_t* ctrl_if = nullptr;
    const audio_codec_gpio_if_t* gpio_if = nullptr;
    const audio_codec_if_t* codec_if = nullptr;
    esp_codec_dev_handle_t dev = nullptr;
    bool ready = false;
};

ProbeHardware g_probe;
OutputProbe g_output;
std::array<int16_t, kToneSamples> g_tone{};
std::array<int16_t, kSilenceSamples> g_silence{};

const char* reset_reason_name(esp_reset_reason_t reason)
{
    switch (reason) {
        case ESP_RST_POWERON: return "power-on";
        case ESP_RST_EXT: return "external-reset";
        case ESP_RST_SW: return "software-reset";
        case ESP_RST_PANIC: return "panic";
        case ESP_RST_INT_WDT: return "interrupt-watchdog";
        case ESP_RST_TASK_WDT: return "task-watchdog";
        case ESP_RST_WDT: return "other-watchdog";
        case ESP_RST_DEEPSLEEP: return "deep-sleep";
        case ESP_RST_BROWNOUT: return "brownout";
        case ESP_RST_SDIO: return "sdio";
        case ESP_RST_UNKNOWN:
        default: return "unknown-or-other";
    }
}

void make_device_id(char* output, std::size_t output_size)
{
    uint8_t mac[6]{};
    if (esp_efuse_mac_get_default(mac) != ESP_OK) {
        std::snprintf(output, output_size, "esp32s3-unknown");
        return;
    }

    std::snprintf(output,
                  output_size,
                  "esp32s3-%02X%02X%02X%02X%02X%02X",
                  mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

i2c_master_dev_handle_t add_i2c_device(uint8_t address)
{
    i2c_device_config_t config{};
    config.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    config.device_address = address;
    config.scl_speed_hz = 400000;

    i2c_master_dev_handle_t handle = nullptr;
    ESP_ERROR_CHECK(i2c_master_bus_add_device(g_probe.i2c_bus, &config, &handle));
    return handle;
}

void write_reg(i2c_master_dev_handle_t device, uint8_t reg, uint8_t value)
{
    const uint8_t payload[2] = {reg, value};
    ESP_ERROR_CHECK(i2c_master_transmit(device, payload, sizeof(payload), kI2cTimeoutMs));
}

uint8_t read_reg(i2c_master_dev_handle_t device, uint8_t reg)
{
    uint8_t value = 0;
    ESP_ERROR_CHECK(i2c_master_transmit_receive(device, &reg, 1, &value, 1, kI2cTimeoutMs));
    return value;
}

void initialise_control_bus()
{
    i2c_master_bus_config_t config{};
    config.i2c_port = I2C_NUM_1;
    config.sda_io_num = kI2cSda;
    config.scl_io_num = kI2cScl;
    config.clk_source = I2C_CLK_SRC_DEFAULT;
    config.glitch_ignore_cnt = 7;
    config.flags.enable_internal_pullup = true;
    ESP_ERROR_CHECK(i2c_new_master_bus(&config, &g_probe.i2c_bus));

    g_probe.pmic = add_i2c_device(kAxp2101Address);
    g_probe.io_expander = add_i2c_device(kAw9523Address);

    uint8_t rail = read_reg(g_probe.pmic, 0x90);
    write_reg(g_probe.pmic, 0x90, rail | 0xB4);
    write_reg(g_probe.pmic, 0x97, 28);
    write_reg(g_probe.pmic, 0x69, 0x35);
    write_reg(g_probe.pmic, 0x30, 0x3F);
    write_reg(g_probe.pmic, 0x90, 0xBF);
    write_reg(g_probe.pmic, 0x94, 28);
    write_reg(g_probe.pmic, 0x95, 28);
    write_reg(g_probe.pmic, 0x27, 0x00);

    rail = read_reg(g_probe.pmic, 0x90);
    write_reg(g_probe.pmic, 0x90, rail & 0x7F);

    write_reg(g_probe.io_expander, 0x02, 0x07);
    write_reg(g_probe.io_expander, 0x03, 0x8F);
    write_reg(g_probe.io_expander, 0x04, 0x18);
    write_reg(g_probe.io_expander, 0x05, 0x0C);
    write_reg(g_probe.io_expander, 0x11, 0x10);
    write_reg(g_probe.io_expander, 0x12, 0xFF);
    write_reg(g_probe.io_expander, 0x13, 0xFF);
}

void reset_output_endpoint()
{
    write_reg(g_probe.io_expander, 0x02, 0x03);
    vTaskDelay(pdMS_TO_TICKS(10));
    write_reg(g_probe.io_expander, 0x02, 0x07);
    vTaskDelay(pdMS_TO_TICKS(50));
}

void initialise_output_path()
{
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    chan_cfg.dma_desc_num = 6;
    chan_cfg.dma_frame_num = 240;
    ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, &g_output.tx, nullptr));

    i2s_std_config_t std_cfg{};
    std_cfg.clk_cfg.sample_rate_hz = kade_body_contract::kAudioSampleRateHz;
    std_cfg.clk_cfg.clk_src = I2S_CLK_SRC_DEFAULT;
    std_cfg.clk_cfg.mclk_multiple = I2S_MCLK_MULTIPLE_256;

    std_cfg.slot_cfg.data_bit_width = I2S_DATA_BIT_WIDTH_16BIT;
    std_cfg.slot_cfg.slot_bit_width = I2S_SLOT_BIT_WIDTH_AUTO;
    std_cfg.slot_cfg.slot_mode = I2S_SLOT_MODE_STEREO;
    std_cfg.slot_cfg.slot_mask = I2S_STD_SLOT_BOTH;
    std_cfg.slot_cfg.ws_width = I2S_DATA_BIT_WIDTH_16BIT;
    std_cfg.slot_cfg.ws_pol = false;
    std_cfg.slot_cfg.bit_shift = true;
    std_cfg.slot_cfg.left_align = true;
    std_cfg.slot_cfg.big_endian = false;
    std_cfg.slot_cfg.bit_order_lsb = false;

    std_cfg.gpio_cfg.mclk = kAudioMclk;
    std_cfg.gpio_cfg.bclk = kAudioBclk;
    std_cfg.gpio_cfg.ws = kAudioWs;
    std_cfg.gpio_cfg.dout = kAudioDout;
    std_cfg.gpio_cfg.din = I2S_GPIO_UNUSED;
    std_cfg.gpio_cfg.invert_flags.mclk_inv = false;
    std_cfg.gpio_cfg.invert_flags.bclk_inv = false;
    std_cfg.gpio_cfg.invert_flags.ws_inv = false;

    ESP_ERROR_CHECK(i2s_channel_init_std_mode(g_output.tx, &std_cfg));
    ESP_ERROR_CHECK(i2s_channel_enable(g_output.tx));

    audio_codec_i2s_cfg_t data_cfg{};
    data_cfg.port = I2S_NUM_0;
    data_cfg.rx_handle = nullptr;
    data_cfg.tx_handle = g_output.tx;
    g_output.data_if = audio_codec_new_i2s_data(&data_cfg);
    if (g_output.data_if == nullptr) {
        ESP_LOGE(kLogTag, "PROBE5 status=failed stage=data-interface");
        return;
    }

    audio_codec_i2c_cfg_t ctrl_cfg{};
    ctrl_cfg.port = I2C_NUM_1;
    ctrl_cfg.addr = AW88298_CODEC_DEFAULT_ADDR;
    ctrl_cfg.bus_handle = g_probe.i2c_bus;
    g_output.ctrl_if = audio_codec_new_i2c_ctrl(&ctrl_cfg);
    if (g_output.ctrl_if == nullptr) {
        ESP_LOGE(kLogTag, "PROBE5 status=failed stage=control-interface");
        return;
    }

    g_output.gpio_if = audio_codec_new_gpio();
    if (g_output.gpio_if == nullptr) {
        ESP_LOGE(kLogTag, "PROBE5 status=failed stage=gpio-interface");
        return;
    }

    aw88298_codec_cfg_t codec_cfg{};
    codec_cfg.ctrl_if = g_output.ctrl_if;
    codec_cfg.gpio_if = g_output.gpio_if;
    codec_cfg.reset_pin = GPIO_NUM_NC;
    codec_cfg.hw_gain.pa_voltage = 5.0f;
    codec_cfg.hw_gain.codec_dac_voltage = 3.3f;
    codec_cfg.hw_gain.pa_gain = 1;
    g_output.codec_if = aw88298_codec_new(&codec_cfg);
    if (g_output.codec_if == nullptr) {
        ESP_LOGE(kLogTag, "PROBE5 status=failed stage=codec-interface");
        return;
    }

    esp_codec_dev_cfg_t dev_cfg{};
    dev_cfg.dev_type = ESP_CODEC_DEV_TYPE_OUT;
    dev_cfg.codec_if = g_output.codec_if;
    dev_cfg.data_if = g_output.data_if;
    g_output.dev = esp_codec_dev_new(&dev_cfg);
    if (g_output.dev == nullptr) {
        ESP_LOGE(kLogTag, "PROBE5 status=failed stage=device");
        return;
    }

    esp_codec_dev_sample_info_t sample_info{};
    sample_info.bits_per_sample = 16;
    sample_info.channel = 1;
    sample_info.channel_mask = 0;
    sample_info.sample_rate = kade_body_contract::kAudioSampleRateHz;
    sample_info.mclk_multiple = 0;

    int open_err = ESP_FAIL;
    for (int attempt = 1; attempt <= kOpenAttempts; ++attempt) {
        open_err = esp_codec_dev_open(g_output.dev, &sample_info);
        if (open_err == ESP_OK) break;
        ESP_LOGW(kLogTag, "PROBE5_OPEN attempt=%d/%d err=%s",
                 attempt, kOpenAttempts, esp_err_to_name(static_cast<esp_err_t>(open_err)));
        if (attempt < kOpenAttempts) vTaskDelay(pdMS_TO_TICKS(25));
    }
    if (open_err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE5 status=failed stage=open err=%s",
                 esp_err_to_name(static_cast<esp_err_t>(open_err)));
        return;
    }

    const int volume_err = esp_codec_dev_set_out_vol(g_output.dev, kOutputVolume);
    if (volume_err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE5 status=failed stage=volume err=%s",
                 esp_err_to_name(static_cast<esp_err_t>(volume_err)));
        ESP_ERROR_CHECK_WITHOUT_ABORT(esp_codec_dev_close(g_output.dev));
        return;
    }

    g_output.ready = true;
    ESP_LOGI(kLogTag, "PROBE5 status=ready sample_rate=%d body_channels=%d",
             kade_body_contract::kAudioSampleRateHz,
             kade_body_contract::kAudioChannels);
}

void build_probe_signal()
{
    for (int i = 0; i < kToneSamples; ++i) {
        const int phase = i % 40;
        int value = 0;
        if (phase < 10) {
            value = phase * 1200;
        } else if (phase < 20) {
            value = (19 - phase) * 1200;
        } else if (phase < 30) {
            value = -(phase - 20) * 1200;
        } else {
            value = -(39 - phase) * 1200;
        }
        g_tone[static_cast<std::size_t>(i)] = static_cast<int16_t>(value);
    }
}

void run_output_probe()
{
    if (!g_output.ready) return;

    build_probe_signal();
    vTaskDelay(pdMS_TO_TICKS(120));

    const int write_err = esp_codec_dev_write(
        g_output.dev,
        g_tone.data(),
        static_cast<int>(g_tone.size() * sizeof(int16_t)));
    if (write_err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE5 status=failed stage=write err=%s",
                 esp_err_to_name(static_cast<esp_err_t>(write_err)));
    } else {
        const int silence_err = esp_codec_dev_write(
            g_output.dev,
            g_silence.data(),
            static_cast<int>(g_silence.size() * sizeof(int16_t)));
        if (silence_err != ESP_OK) {
            ESP_LOGW(kLogTag, "PROBE5 silence_write err=%s",
                     esp_err_to_name(static_cast<esp_err_t>(silence_err)));
        }
        ESP_LOGI(kLogTag, "PROBE5 status=complete bytes=%u",
                 static_cast<unsigned>(g_tone.size() * sizeof(int16_t)));
    }

    const int mute_err = esp_codec_dev_set_out_mute(g_output.dev, true);
    if (mute_err != ESP_OK) {
        ESP_LOGW(kLogTag, "PROBE5 mute err=%s",
                 esp_err_to_name(static_cast<esp_err_t>(mute_err)));
    }
    const int close_err = esp_codec_dev_close(g_output.dev);
    if (close_err != ESP_OK) {
        ESP_LOGW(kLogTag, "PROBE5 close err=%s",
                 esp_err_to_name(static_cast<esp_err_t>(close_err)));
    }
}

void log_contract()
{
    using namespace kade_body_contract;
    ESP_LOGI(kLogTag,
             "BODY_CONTRACT protocol=1 display=%dx%d audio=%dHz/%dch yaw=[%d,%d] pitch=[%d,%d] speed=[%d,%d] tolerance=%d",
             kDisplayWidth, kDisplayHeight, kAudioSampleRateHz, kAudioChannels,
             kSafeYawMinTenths, kSafeYawMaxTenths, kSafePitchMinTenths, kSafePitchMaxTenths,
             kMinMotionSpeed, kMaxMotionSpeed, kPositionToleranceTenths);
    ESP_LOGI(kLogTag,
             "BODY_POLICY preserve_zero=%d release_torque=%d motion_driver=off display_driver=off input_path=off network=off",
             kPreserveStoredZeroCalibration ? 1 : 0,
             kReleaseTorqueAfterMotion ? 1 : 0);
}

}  // namespace

extern "C" void app_main(void)
{
    char device_id[32]{};
    make_device_id(device_id, sizeof(device_id));

    const esp_app_desc_t* app = esp_app_get_description();
    ESP_LOGI(kLogTag,
             "BODY_BOOT firmware=%s device_id=%s reset=%s",
             app != nullptr ? app->version : "unknown",
             device_id,
             reset_reason_name(esp_reset_reason()));
    log_contract();

    ESP_LOGI(kLogTag, "PROBE5 phase=control-bus");
    initialise_control_bus();
    reset_output_endpoint();
    ESP_LOGI(kLogTag, "PROBE5 phase=data-path");
    initialise_output_path();
    run_output_probe();

    uint32_t heartbeat_sequence = 0;
    while (true) {
        const uint64_t now_ms = static_cast<uint64_t>(esp_timer_get_time()) / 1000ULL;
        ESP_LOGI(kLogTag,
                 "BODY_HEARTBEAT seq=%" PRIu32 " uptime_ms=%" PRIu64 " free_heap=%" PRIu32,
                 heartbeat_sequence++,
                 now_ms,
                 esp_get_free_heap_size());
        vTaskDelay(pdMS_TO_TICKS(kHeartbeatMs));
    }
}
