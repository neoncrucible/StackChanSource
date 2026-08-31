#include "body_contract.h"

#include <algorithm>
#include <array>
#include <cinttypes>
#include <cstdint>
#include <cstdio>

#include "driver/i2c_master.h"
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
constexpr uint32_t kSampleReportMs = 1000;
constexpr int kI2cTimeoutMs = 250;

constexpr gpio_num_t kI2cSda = GPIO_NUM_12;
constexpr gpio_num_t kI2cScl = GPIO_NUM_11;
constexpr uint8_t kAxp2101Address = 0x34;
constexpr uint8_t kAw9523Address = 0x58;

constexpr gpio_num_t kAudioMclk = GPIO_NUM_0;
constexpr gpio_num_t kAudioWs = GPIO_NUM_33;
constexpr gpio_num_t kAudioBclk = GPIO_NUM_34;
constexpr gpio_num_t kAudioDin = GPIO_NUM_14;

struct ProbeHardware {
    i2c_master_bus_handle_t i2c_bus = nullptr;
    i2c_master_dev_handle_t pmic = nullptr;
    i2c_master_dev_handle_t io_expander = nullptr;
};

struct AudioProbe {
    i2s_chan_handle_t rx = nullptr;
    const audio_codec_data_if_t* data_if = nullptr;
    const audio_codec_ctrl_if_t* input_ctrl_if = nullptr;
    const audio_codec_if_t* input_codec_if = nullptr;
    esp_codec_dev_handle_t input_dev = nullptr;
    bool ready = false;
};

ProbeHardware g_probe;
AudioProbe g_audio;
std::array<int16_t, 4096> g_samples{};

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

    // Keep the display rail dark; this checkpoint owns no screen output.
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

void initialise_input_path()
{
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    chan_cfg.dma_desc_num = 6;
    chan_cfg.dma_frame_num = 240;
    ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, nullptr, &g_audio.rx));

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

    ESP_ERROR_CHECK(i2s_channel_init_tdm_mode(g_audio.rx, &tdm_cfg));
    ESP_ERROR_CHECK(i2s_channel_enable(g_audio.rx));

    audio_codec_i2s_cfg_t data_cfg{};
    data_cfg.port = I2S_NUM_0;
    data_cfg.rx_handle = g_audio.rx;
    data_cfg.tx_handle = nullptr;
    g_audio.data_if = audio_codec_new_i2s_data(&data_cfg);
    if (g_audio.data_if == nullptr) {
        ESP_LOGE(kLogTag, "PROBE4 status=failed stage=data-interface");
        return;
    }

    audio_codec_i2c_cfg_t ctrl_cfg{};
    ctrl_cfg.port = I2C_NUM_1;
    ctrl_cfg.addr = ES7210_CODEC_DEFAULT_ADDR;
    ctrl_cfg.bus_handle = g_probe.i2c_bus;
    g_audio.input_ctrl_if = audio_codec_new_i2c_ctrl(&ctrl_cfg);
    if (g_audio.input_ctrl_if == nullptr) {
        ESP_LOGE(kLogTag, "PROBE4 status=failed stage=control-interface");
        return;
    }

    es7210_codec_cfg_t codec_cfg{};
    codec_cfg.ctrl_if = g_audio.input_ctrl_if;
    codec_cfg.master_mode = false;
    codec_cfg.mic_selected = ES7210_SEL_MIC1 | ES7210_SEL_MIC2 | ES7210_SEL_MIC3;
    codec_cfg.mclk_src = ES7210_MCLK_FROM_PAD;
    codec_cfg.mclk_div = 256;
    g_audio.input_codec_if = es7210_codec_new(&codec_cfg);
    if (g_audio.input_codec_if == nullptr) {
        ESP_LOGE(kLogTag, "PROBE4 status=failed stage=codec-interface");
        return;
    }

    esp_codec_dev_cfg_t dev_cfg{};
    dev_cfg.dev_type = ESP_CODEC_DEV_TYPE_IN;
    dev_cfg.codec_if = g_audio.input_codec_if;
    dev_cfg.data_if = g_audio.data_if;
    g_audio.input_dev = esp_codec_dev_new(&dev_cfg);
    if (g_audio.input_dev == nullptr) {
        ESP_LOGE(kLogTag, "PROBE4 status=failed stage=device");
        return;
    }

    esp_codec_dev_sample_info_t sample_info{};
    sample_info.bits_per_sample = 16;
    sample_info.channel = 2;
    sample_info.channel_mask = ESP_CODEC_DEV_MAKE_CHANNEL_MASK(0) |
                               ESP_CODEC_DEV_MAKE_CHANNEL_MASK(1);
    sample_info.sample_rate = kade_body_contract::kAudioSampleRateHz;
    sample_info.mclk_multiple = 0;

    const esp_err_t open_err = esp_codec_dev_open(g_audio.input_dev, &sample_info);
    if (open_err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE4 status=failed stage=open err=%s", esp_err_to_name(open_err));
        return;
    }

    const esp_err_t gain_err = esp_codec_dev_set_in_channel_gain(
        g_audio.input_dev,
        ESP_CODEC_DEV_MAKE_CHANNEL_MASK(0),
        45.0f);
    if (gain_err != ESP_OK) {
        ESP_LOGW(kLogTag, "PROBE4 gain_setup err=%s", esp_err_to_name(gain_err));
    }

    g_audio.ready = true;
    ESP_LOGI(kLogTag,
             "PROBE4 status=ready sample_rate=%d physical_channels=2 body_channels=%d",
             kade_body_contract::kAudioSampleRateHz,
             kade_body_contract::kAudioChannels);
}

void sample_input(uint32_t sequence)
{
    if (!g_audio.ready) return;

    const esp_err_t err = esp_codec_dev_read(
        g_audio.input_dev,
        g_samples.data(),
        static_cast<int>(g_samples.size() * sizeof(int16_t)));
    if (err != ESP_OK) {
        ESP_LOGW(kLogTag, "PROBE4_SAMPLE seq=%" PRIu32 " status=read-error err=%s",
                 sequence, esp_err_to_name(err));
        return;
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
             "PROBE4_SAMPLE seq=%" PRIu32 " status=ok peak=%d mean_abs=%" PRIu32,
             sequence, peak, mean_abs);
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
             "BODY_POLICY preserve_zero=%d release_torque=%d motion_driver=off display_driver=off output_path=off network=off",
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

    ESP_LOGI(kLogTag, "PROBE4 phase=control-bus");
    initialise_control_bus();
    ESP_LOGI(kLogTag, "PROBE4 phase=data-path");
    initialise_input_path();

    uint32_t heartbeat_sequence = 0;
    uint32_t sample_sequence = 0;
    uint64_t next_heartbeat_ms = 0;
    uint64_t next_sample_ms = 0;

    while (true) {
        const uint64_t now_ms = static_cast<uint64_t>(esp_timer_get_time()) / 1000ULL;

        if (now_ms >= next_sample_ms) {
            sample_input(sample_sequence++);
            next_sample_ms = now_ms + kSampleReportMs;
        }

        if (now_ms >= next_heartbeat_ms) {
            ESP_LOGI(kLogTag,
                     "BODY_HEARTBEAT seq=%" PRIu32 " uptime_ms=%" PRIu64 " free_heap=%" PRIu32,
                     heartbeat_sequence++,
                     now_ms,
                     esp_get_free_heap_size());
            next_heartbeat_ms = now_ms + kHeartbeatMs;
        }

        vTaskDelay(pdMS_TO_TICKS(20));
    }
}
