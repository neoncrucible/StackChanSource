#include "body_contract.h"

#include <algorithm>
#include <array>
#include <cinttypes>
#include <cstdint>
#include <cstdio>

#include "driver/i2c_master.h"
#include "driver/i2s_std.h"
#include "driver/i2s_tdm.h"
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
constexpr int kOutputVolume = 55;
constexpr int kToneSamples = 8000;
constexpr int kSilenceSamples = 800;

constexpr gpio_num_t kI2cSda = GPIO_NUM_12;
constexpr gpio_num_t kI2cScl = GPIO_NUM_11;
constexpr uint8_t kAxp2101Address = 0x34;
constexpr uint8_t kAw9523Address = 0x58;

constexpr gpio_num_t kAudioMclk = GPIO_NUM_0;
constexpr gpio_num_t kAudioWs = GPIO_NUM_33;
constexpr gpio_num_t kAudioBclk = GPIO_NUM_34;
constexpr gpio_num_t kAudioDout = GPIO_NUM_13;
constexpr gpio_num_t kAudioDin = GPIO_NUM_14;

struct ControlHardware {
    i2c_master_bus_handle_t i2c_bus = nullptr;
    i2c_master_dev_handle_t pmic = nullptr;
    i2c_master_dev_handle_t io_expander = nullptr;
};

struct AudioTransport {
    i2s_chan_handle_t rx = nullptr;
    i2s_chan_handle_t tx = nullptr;
    const audio_codec_data_if_t* data_if = nullptr;

    const audio_codec_ctrl_if_t* input_ctrl_if = nullptr;
    const audio_codec_if_t* input_codec_if = nullptr;
    esp_codec_dev_handle_t input_dev = nullptr;

    const audio_codec_ctrl_if_t* output_ctrl_if = nullptr;
    const audio_codec_gpio_if_t* output_gpio_if = nullptr;
    const audio_codec_if_t* output_codec_if = nullptr;
    esp_codec_dev_handle_t output_dev = nullptr;

    bool ready = false;
};

ControlHardware g_control;
AudioTransport g_audio;
std::array<int16_t, 4096> g_samples{};
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
    ESP_ERROR_CHECK(i2c_master_bus_add_device(g_control.i2c_bus, &config, &handle));
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
    ESP_ERROR_CHECK(i2c_new_master_bus(&config, &g_control.i2c_bus));

    g_control.pmic = add_i2c_device(kAxp2101Address);
    g_control.io_expander = add_i2c_device(kAw9523Address);

    uint8_t rail = read_reg(g_control.pmic, 0x90);
    write_reg(g_control.pmic, 0x90, rail | 0xB4);
    write_reg(g_control.pmic, 0x97, 28);
    write_reg(g_control.pmic, 0x69, 0x35);
    write_reg(g_control.pmic, 0x30, 0x3F);
    write_reg(g_control.pmic, 0x90, 0xBF);
    write_reg(g_control.pmic, 0x94, 28);
    write_reg(g_control.pmic, 0x95, 28);
    write_reg(g_control.pmic, 0x27, 0x00);

    rail = read_reg(g_control.pmic, 0x90);
    write_reg(g_control.pmic, 0x90, rail & 0x7F);

    write_reg(g_control.io_expander, 0x02, 0x07);
    write_reg(g_control.io_expander, 0x03, 0x8F);
    write_reg(g_control.io_expander, 0x04, 0x18);
    write_reg(g_control.io_expander, 0x05, 0x0C);
    write_reg(g_control.io_expander, 0x11, 0x10);
    write_reg(g_control.io_expander, 0x12, 0xFF);
    write_reg(g_control.io_expander, 0x13, 0xFF);
}

void reset_output_endpoint()
{
    write_reg(g_control.io_expander, 0x02, 0x03);
    vTaskDelay(pdMS_TO_TICKS(10));
    write_reg(g_control.io_expander, 0x02, 0x07);
    vTaskDelay(pdMS_TO_TICKS(50));
}

bool initialise_transport()
{
    reset_output_endpoint();

    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    chan_cfg.dma_desc_num = 6;
    chan_cfg.dma_frame_num = 240;
    if (i2s_new_channel(&chan_cfg, &g_audio.tx, &g_audio.rx) != ESP_OK) return false;

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

    i2s_tdm_config_t tdm_cfg{};
    tdm_cfg.clk_cfg.sample_rate_hz = kade_body_contract::kAudioSampleRateHz;
    tdm_cfg.clk_cfg.clk_src = I2S_CLK_SRC_DEFAULT;
    tdm_cfg.clk_cfg.mclk_multiple = I2S_MCLK_MULTIPLE_256;
    tdm_cfg.clk_cfg.bclk_div = 8;
    tdm_cfg.slot_cfg.data_bit_width = I2S_DATA_BIT_WIDTH_16BIT;
    tdm_cfg.slot_cfg.slot_bit_width = I2S_SLOT_BIT_WIDTH_AUTO;
    tdm_cfg.slot_cfg.slot_mode = I2S_SLOT_MODE_STEREO;
    tdm_cfg.slot_cfg.slot_mask = static_cast<i2s_tdm_slot_mask_t>(
        I2S_TDM_SLOT0 | I2S_TDM_SLOT1 | I2S_TDM_SLOT2 | I2S_TDM_SLOT3);
    tdm_cfg.slot_cfg.ws_width = I2S_TDM_AUTO_WS_WIDTH;
    tdm_cfg.slot_cfg.ws_pol = false;
    tdm_cfg.slot_cfg.bit_shift = true;
    tdm_cfg.slot_cfg.left_align = false;
    tdm_cfg.slot_cfg.big_endian = false;
    tdm_cfg.slot_cfg.bit_order_lsb = false;
    tdm_cfg.slot_cfg.skip_mask = false;
    tdm_cfg.slot_cfg.total_slot = I2S_TDM_AUTO_SLOT_NUM;
    tdm_cfg.gpio_cfg.mclk = kAudioMclk;
    tdm_cfg.gpio_cfg.bclk = kAudioBclk;
    tdm_cfg.gpio_cfg.ws = kAudioWs;
    tdm_cfg.gpio_cfg.dout = I2S_GPIO_UNUSED;
    tdm_cfg.gpio_cfg.din = kAudioDin;
    tdm_cfg.gpio_cfg.invert_flags.mclk_inv = false;
    tdm_cfg.gpio_cfg.invert_flags.bclk_inv = false;
    tdm_cfg.gpio_cfg.invert_flags.ws_inv = false;

    if (i2s_channel_init_std_mode(g_audio.tx, &std_cfg) != ESP_OK) return false;
    if (i2s_channel_init_tdm_mode(g_audio.rx, &tdm_cfg) != ESP_OK) return false;
    if (i2s_channel_enable(g_audio.tx) != ESP_OK) return false;
    if (i2s_channel_enable(g_audio.rx) != ESP_OK) return false;

    audio_codec_i2s_cfg_t data_cfg{};
    data_cfg.port = I2S_NUM_0;
    data_cfg.rx_handle = g_audio.rx;
    data_cfg.tx_handle = g_audio.tx;
    g_audio.data_if = audio_codec_new_i2s_data(&data_cfg);
    if (g_audio.data_if == nullptr) return false;

    audio_codec_i2c_cfg_t ctrl_cfg{};
    ctrl_cfg.port = I2C_NUM_1;
    ctrl_cfg.bus_handle = g_control.i2c_bus;

    ctrl_cfg.addr = AW88298_CODEC_DEFAULT_ADDR;
    g_audio.output_ctrl_if = audio_codec_new_i2c_ctrl(&ctrl_cfg);
    if (g_audio.output_ctrl_if == nullptr) return false;
    g_audio.output_gpio_if = audio_codec_new_gpio();
    if (g_audio.output_gpio_if == nullptr) return false;

    aw88298_codec_cfg_t output_codec_cfg{};
    output_codec_cfg.ctrl_if = g_audio.output_ctrl_if;
    output_codec_cfg.gpio_if = g_audio.output_gpio_if;
    output_codec_cfg.reset_pin = GPIO_NUM_NC;
    output_codec_cfg.hw_gain.pa_voltage = 5.0f;
    output_codec_cfg.hw_gain.codec_dac_voltage = 3.3f;
    output_codec_cfg.hw_gain.pa_gain = 1;
    g_audio.output_codec_if = aw88298_codec_new(&output_codec_cfg);
    if (g_audio.output_codec_if == nullptr) return false;

    esp_codec_dev_cfg_t output_dev_cfg{};
    output_dev_cfg.dev_type = ESP_CODEC_DEV_TYPE_OUT;
    output_dev_cfg.codec_if = g_audio.output_codec_if;
    output_dev_cfg.data_if = g_audio.data_if;
    g_audio.output_dev = esp_codec_dev_new(&output_dev_cfg);
    if (g_audio.output_dev == nullptr) return false;

    ctrl_cfg.addr = ES7210_CODEC_DEFAULT_ADDR;
    g_audio.input_ctrl_if = audio_codec_new_i2c_ctrl(&ctrl_cfg);
    if (g_audio.input_ctrl_if == nullptr) return false;

    es7210_codec_cfg_t input_codec_cfg{};
    input_codec_cfg.ctrl_if = g_audio.input_ctrl_if;
    input_codec_cfg.master_mode = false;
    input_codec_cfg.mic_selected = ES7210_SEL_MIC1 | ES7210_SEL_MIC2 | ES7210_SEL_MIC3;
    input_codec_cfg.mclk_src = ES7210_MCLK_FROM_PAD;
    input_codec_cfg.mclk_div = 256;
    g_audio.input_codec_if = es7210_codec_new(&input_codec_cfg);
    if (g_audio.input_codec_if == nullptr) return false;

    esp_codec_dev_cfg_t input_dev_cfg{};
    input_dev_cfg.dev_type = ESP_CODEC_DEV_TYPE_IN;
    input_dev_cfg.codec_if = g_audio.input_codec_if;
    input_dev_cfg.data_if = g_audio.data_if;
    g_audio.input_dev = esp_codec_dev_new(&input_dev_cfg);
    if (g_audio.input_dev == nullptr) return false;

    g_audio.ready = true;
    return true;
}

bool open_input()
{
    if (!g_audio.ready || g_audio.input_dev == nullptr) return false;

    esp_codec_dev_sample_info_t sample_info{};
    sample_info.bits_per_sample = 16;
    sample_info.channel = 2;
    sample_info.channel_mask = ESP_CODEC_DEV_MAKE_CHANNEL_MASK(0) |
                               ESP_CODEC_DEV_MAKE_CHANNEL_MASK(1);
    sample_info.sample_rate = kade_body_contract::kAudioSampleRateHz;
    sample_info.mclk_multiple = 0;

    const esp_err_t open_err = static_cast<esp_err_t>(esp_codec_dev_open(g_audio.input_dev, &sample_info));
    if (open_err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE7 input-open err=%s", esp_err_to_name(open_err));
        return false;
    }

    const esp_err_t gain_err = static_cast<esp_err_t>(esp_codec_dev_set_in_channel_gain(
        g_audio.input_dev,
        ESP_CODEC_DEV_MAKE_CHANNEL_MASK(0),
        45.0f));
    if (gain_err != ESP_OK) {
        ESP_LOGW(kLogTag, "PROBE7 input-gain err=%s", esp_err_to_name(gain_err));
    }
    return true;
}

bool sample_input(const char* label)
{
    const esp_err_t err = static_cast<esp_err_t>(esp_codec_dev_read(
        g_audio.input_dev,
        g_samples.data(),
        static_cast<int>(g_samples.size() * sizeof(int16_t))));
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE7 %s status=failed stage=read err=%s", label, esp_err_to_name(err));
        return false;
    }

    int peak = 0;
    uint64_t sum_abs = 0;
    for (const int16_t sample : g_samples) {
        const int value = sample == INT16_MIN ? 32768 : std::abs(static_cast<int>(sample));
        peak = std::max(peak, value);
        sum_abs += static_cast<uint64_t>(value);
    }
    const uint32_t mean_abs = static_cast<uint32_t>(sum_abs / g_samples.size());

    ESP_LOGI(kLogTag,
             "PROBE7 %s status=ok peak=%d mean_abs=%" PRIu32,
             label,
             peak,
             mean_abs);
    return true;
}

bool close_input()
{
    const esp_err_t err = static_cast<esp_err_t>(esp_codec_dev_close(g_audio.input_dev));
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE7 input-close err=%s", esp_err_to_name(err));
        return false;
    }
    return true;
}

bool open_output()
{
    if (!g_audio.ready || g_audio.output_dev == nullptr) return false;

    esp_codec_dev_sample_info_t sample_info{};
    sample_info.bits_per_sample = 16;
    sample_info.channel = 1;
    sample_info.channel_mask = 0;
    sample_info.sample_rate = kade_body_contract::kAudioSampleRateHz;
    sample_info.mclk_multiple = 0;

    esp_err_t open_err = ESP_FAIL;
    for (int attempt = 1; attempt <= kOpenAttempts; ++attempt) {
        open_err = static_cast<esp_err_t>(esp_codec_dev_open(g_audio.output_dev, &sample_info));
        if (open_err == ESP_OK) break;
        ESP_LOGW(kLogTag,
                 "PROBE7 output-open attempt=%d/%d err=%s",
                 attempt,
                 kOpenAttempts,
                 esp_err_to_name(open_err));
        if (attempt < kOpenAttempts) vTaskDelay(pdMS_TO_TICKS(25));
    }
    if (open_err != ESP_OK) return false;

    const esp_err_t volume_err = static_cast<esp_err_t>(esp_codec_dev_set_out_vol(g_audio.output_dev, kOutputVolume));
    if (volume_err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE7 output-volume err=%s", esp_err_to_name(volume_err));
        ESP_ERROR_CHECK_WITHOUT_ABORT(esp_codec_dev_close(g_audio.output_dev));
        return false;
    }
    return true;
}

void build_probe_signal()
{
    for (int i = 0; i < kToneSamples; ++i) {
        const int phase = i % 40;
        int value = 0;
        if (phase < 10) {
            value = phase * 1000;
        } else if (phase < 20) {
            value = (19 - phase) * 1000;
        } else if (phase < 30) {
            value = -(phase - 20) * 1000;
        } else {
            value = -(39 - phase) * 1000;
        }
        g_tone[static_cast<std::size_t>(i)] = static_cast<int16_t>(value);
    }
}

bool run_output()
{
    build_probe_signal();
    vTaskDelay(pdMS_TO_TICKS(120));

    const esp_err_t write_err = static_cast<esp_err_t>(esp_codec_dev_write(
        g_audio.output_dev,
        g_tone.data(),
        static_cast<int>(g_tone.size() * sizeof(int16_t))));
    if (write_err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE7 output-write err=%s", esp_err_to_name(write_err));
        return false;
    }

    const esp_err_t silence_err = static_cast<esp_err_t>(esp_codec_dev_write(
        g_audio.output_dev,
        g_silence.data(),
        static_cast<int>(g_silence.size() * sizeof(int16_t))));
    if (silence_err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE7 output-silence err=%s", esp_err_to_name(silence_err));
        return false;
    }

    ESP_LOGI(kLogTag,
             "PROBE7 stage-b status=ok bytes=%u",
             static_cast<unsigned>(g_tone.size() * sizeof(int16_t)));
    return true;
}

bool close_output()
{
    const esp_err_t mute_err = static_cast<esp_err_t>(esp_codec_dev_set_out_mute(g_audio.output_dev, true));
    if (mute_err != ESP_OK) {
        ESP_LOGW(kLogTag, "PROBE7 output-mute err=%s", esp_err_to_name(mute_err));
    }

    const esp_err_t close_err = static_cast<esp_err_t>(esp_codec_dev_close(g_audio.output_dev));
    if (close_err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE7 output-close err=%s", esp_err_to_name(close_err));
        return false;
    }
    return true;
}

bool run_probe7()
{
    ESP_LOGI(kLogTag, "PROBE7 phase=control");
    initialise_control_bus();

    ESP_LOGI(kLogTag, "PROBE7 phase=transport");
    if (!initialise_transport()) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=transport-init");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE7 phase=stage-a");
    if (!open_input()) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=stage-a-open");
        return false;
    }
    if (!sample_input("stage-a")) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=stage-a-sample");
        return false;
    }
    if (!close_input()) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=stage-a-close");
        return false;
    }

    vTaskDelay(pdMS_TO_TICKS(100));

    ESP_LOGI(kLogTag, "PROBE7 phase=stage-b");
    if (!open_output()) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=stage-b-open");
        return false;
    }
    if (!run_output()) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=stage-b-run");
        ESP_ERROR_CHECK_WITHOUT_ABORT(esp_codec_dev_close(g_audio.output_dev));
        return false;
    }
    if (!close_output()) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=stage-b-close");
        return false;
    }

    vTaskDelay(pdMS_TO_TICKS(150));

    ESP_LOGI(kLogTag, "PROBE7 phase=stage-c");
    if (!open_input()) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=stage-c-open");
        return false;
    }
    if (!sample_input("stage-c")) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=stage-c-sample");
        return false;
    }
    if (!close_input()) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=stage-c-close");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE7 status=complete sequence=3 transport=persistent");
    return true;
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
             "BODY_POLICY preserve_zero=%d release_torque=%d display_driver=off motion_driver=off network=off one_shot=1",
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

    const bool passed = run_probe7();

    uint32_t heartbeat_seq = 0;
    const int64_t start_us = esp_timer_get_time();
    while (true) {
        const uint32_t uptime_ms = static_cast<uint32_t>((esp_timer_get_time() - start_us) / 1000);
        ESP_LOGI(kLogTag,
                 "BODY_HEARTBEAT seq=%" PRIu32 " uptime_ms=%" PRIu32 " free_heap=%" PRIu32 " status=%s",
                 heartbeat_seq++,
                 uptime_ms,
                 static_cast<uint32_t>(esp_get_free_heap_size()),
                 passed ? "ok" : "failed");
        vTaskDelay(pdMS_TO_TICKS(kHeartbeatMs));
    }
}
