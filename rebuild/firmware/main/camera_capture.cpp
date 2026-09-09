// One requested QVGA frame through public ESP-IDF camera APIs. Reuse the
// existing SCCB/I2C bus; never release or recreate the board bus.
#include "esp_cam_ctlr.h"
#include "esp_cam_ctlr_dvp.h"
#include "esp_cam_sensor.h"
extern "C" {
#include "esp_sccb_i2c.h"
}
#include "gc0308.h"
#include "esp_cache.h"
#include "esp_heap_caps.h"
#include "freertos/queue.h"

namespace {
constexpr size_t kCameraBytes=320*240*2;
struct CameraFrame { uint8_t* data=nullptr; size_t size=0; };
struct CameraCaptureState {
    uint8_t* buffer=nullptr;
    QueueHandle_t completed=nullptr;
    std::atomic<bool> wanted{false};
};
CameraCaptureState g_camera_capture;
bool g_camera_poisoned=false;

void camera_diag(const char* stage) {
    ESP_LOGI(kLogTag,
        "CAMERA_DIAG stage=%s stack_min_free_bytes=%u internal_free=%u internal_largest=%u psram_free=%u psram_largest=%u",
        stage,
        static_cast<unsigned>(uxTaskGetStackHighWaterMark(nullptr)),
        static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)),
        static_cast<unsigned>(heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)),
        static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_SPIRAM)),
        static_cast<unsigned>(heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM)));
}

void camera_power_diag() {
    uint8_t pmic_enable=0, pmic_camera=0, expander_output=0, expander_config=0;
    const bool pmic_enable_ok=probe8_try_read(g_control.pmic,0x90,&pmic_enable);
    const bool pmic_camera_ok=probe8_try_read(g_control.pmic,0x94,&pmic_camera);
    const bool expander_output_ok=probe8_try_read(g_control.io_expander,0x03,&expander_output);
    const bool expander_config_ok=probe8_try_read(g_control.io_expander,0x05,&expander_config);
    ESP_LOGI(kLogTag,
        "CAMERA_POWER pmic_enable_ok=%d pmic_enable=0x%02X pmic_camera_ok=%d pmic_camera=0x%02X expander_output_ok=%d expander_output=0x%02X expander_config_ok=%d expander_config=0x%02X",
        pmic_enable_ok?1:0, pmic_enable, pmic_camera_ok?1:0, pmic_camera,
        expander_output_ok?1:0, expander_output, expander_config_ok?1:0, expander_config);
}

bool camera_fail(const char* stage, esp_err_t err=ESP_FAIL) {
    ESP_LOGE(kLogTag,"CAMERA_DIAG failure=%s err=%s",stage,esp_err_to_name(err));
    camera_diag(stage);
    return false;
}

bool IRAM_ATTR camera_get_frame(esp_cam_ctlr_handle_t, esp_cam_ctlr_trans_t* trans, void*) {
    if (g_camera_capture.wanted.exchange(false)) {
        trans->buffer=g_camera_capture.buffer; trans->buflen=kCameraBytes;
    }
    return false;
}
bool IRAM_ATTR camera_frame_done(esp_cam_ctlr_handle_t, esp_cam_ctlr_trans_t* trans, void*) {
    if (trans->buffer!=g_camera_capture.buffer) return false;
    BaseType_t wake=pdFALSE;
    const size_t length=trans->received_size;
    xQueueOverwriteFromISR(g_camera_capture.completed,&length,&wake);
    return wake==pdTRUE;
}

bool camera_capture_frame(CameraFrame& frame) {
    camera_diag("entry");
    if (g_camera_poisoned || voice_cancel_is_requested()) return camera_fail("precondition",ESP_ERR_INVALID_STATE);
    g_camera_active.store(true);
    esp_sccb_io_handle_t sccb=nullptr;
    esp_cam_sensor_device_t* sensor=nullptr;
    esp_cam_ctlr_handle_t controller=nullptr;
    bool enabled=false,started=false,streaming=false;
    g_camera_capture.completed=xQueueCreate(1,sizeof(size_t));
    g_camera_capture.buffer=static_cast<uint8_t*>(heap_caps_aligned_alloc(64,kCameraBytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
    camera_diag("buffers-ready");
    camera_power_diag();
    bool ok=[&]() {
        if (!g_camera_capture.completed || !g_camera_capture.buffer) return camera_fail("buffers",ESP_ERR_NO_MEM);
        sccb_i2c_config_t bus{};
        bus.dev_addr_length=I2C_ADDR_BIT_LEN_7; bus.device_address=GC0308_SCCB_ADDR; bus.scl_speed_hz=100000;
        esp_err_t err=sccb_new_i2c_io(g_control.i2c_bus,&bus,&sccb);
        if (err!=ESP_OK) return camera_fail("sccb-new",err);
        camera_diag("sccb-ready");
        esp_cam_sensor_config_t sensor_config{};
        sensor_config.sccb_handle=sccb; sensor_config.reset_pin=GPIO_NUM_NC; sensor_config.pwdn_pin=GPIO_NUM_NC; sensor_config.xclk_pin=GPIO_NUM_NC;
        sensor=gc0308_detect(&sensor_config);
        if (!sensor) return camera_fail("sensor-detect",ESP_ERR_NOT_FOUND);
        camera_diag("sensor-detected");
        if (voice_cancel_is_requested()) return camera_fail("sensor-cancelled",ESP_ERR_INVALID_STATE);
        err=esp_cam_sensor_set_format(sensor,nullptr);
        if (err!=ESP_OK) return camera_fail("format-set",err);
        camera_diag("format-set");
        esp_cam_sensor_format_t format{};
        err=esp_cam_sensor_get_format(sensor,&format);
        if(err!=ESP_OK) return camera_fail("format-get",err);
        if(format.width!=320 || format.height!=240 || format.format!=ESP_CAM_SENSOR_PIXFORMAT_RGB565) {
            ESP_LOGE(kLogTag,"CAMERA_DIAG failure=format-contract width=%u height=%u format=%d",
                static_cast<unsigned>(format.width),static_cast<unsigned>(format.height),static_cast<int>(format.format));
            return camera_fail("format-contract",ESP_ERR_INVALID_RESPONSE);
        }
        camera_diag("format-ready");
        esp_cam_ctlr_dvp_pin_config_t pins{};
        pins.data_width=CAM_CTLR_DATA_WIDTH_8;
        const gpio_num_t data[]{GPIO_NUM_39,GPIO_NUM_40,GPIO_NUM_41,GPIO_NUM_42,GPIO_NUM_15,GPIO_NUM_16,GPIO_NUM_48,GPIO_NUM_47};
        for(int i=0;i<8;++i) pins.data_io[i]=data[i];
        pins.vsync_io=GPIO_NUM_46; pins.de_io=GPIO_NUM_38; pins.pclk_io=GPIO_NUM_45; pins.xclk_io=GPIO_NUM_NC;
        esp_cam_ctlr_dvp_config_t config{};
        config.ctlr_id=0; config.clk_src=CAM_CLK_SRC_DEFAULT; config.h_res=320; config.v_res=240;
        config.input_data_color_type=CAM_CTLR_COLOR_RGB565; config.cam_data_width=8;
        config.external_xtal=true; config.xclk_freq=20000000; config.dma_burst_size=64; config.pin=&pins;
        // The driver's backup buffer receives warm-up frames. Our one frame is
        // offered once, so DMA cannot overwrite it while the host reads it.
        err=esp_cam_new_dvp_ctlr(&config,&controller);
        if(err!=ESP_OK) return camera_fail("controller-new",err);
        camera_diag("controller-created");
        esp_cam_ctlr_evt_cbs_t callbacks{};
        callbacks.on_get_new_trans=camera_get_frame; callbacks.on_trans_finished=camera_frame_done;
        err=esp_cam_ctlr_register_event_callbacks(controller,&callbacks,nullptr);
        if(err!=ESP_OK) return camera_fail("callbacks",err);
        camera_diag("callbacks-ready");
        err=esp_cam_ctlr_enable(controller);
        if(err!=ESP_OK) return camera_fail("controller-enable",err);
        enabled=true;
        camera_diag("controller-enabled");
        err=esp_cam_ctlr_start(controller);
        if(err!=ESP_OK) return camera_fail("controller-start",err);
        started=true;
        camera_diag("controller-started");
        int on=1;
        err=esp_cam_sensor_ioctl(sensor,ESP_CAM_SENSOR_IOC_S_STREAM,&on);
        if(err!=ESP_OK) return camera_fail("stream-on",err);
        streaming=true;
        camera_diag("stream-on");
        for(int i=0;i<12;++i) { if(voice_cancel_is_requested()) return camera_fail("warmup-cancelled",ESP_ERR_INVALID_STATE); vTaskDelay(pdMS_TO_TICKS(50)); }
        camera_diag("warmup-complete");
        g_camera_capture.wanted.store(true);
        camera_diag("frame-requested");
        size_t received=0;
        for(int i=0;i<30;++i) {
            if(voice_cancel_is_requested()) return camera_fail("frame-cancelled",ESP_ERR_INVALID_STATE);
            if(xQueueReceive(g_camera_capture.completed,&received,pdMS_TO_TICKS(50))==pdTRUE) {
                ESP_LOGI(kLogTag,"CAMERA_DIAG frame_received=%u expected=%u",
                    static_cast<unsigned>(received),static_cast<unsigned>(kCameraBytes));
                camera_diag("frame-received");
                return received==kCameraBytes || camera_fail("frame-size",ESP_ERR_INVALID_SIZE);
            }
        }
        return camera_fail("frame-timeout",ESP_ERR_TIMEOUT);
    }();
    g_camera_capture.wanted.store(false);
    int off=0;
    if(streaming) {
        const esp_err_t err=esp_cam_sensor_ioctl(sensor,ESP_CAM_SENSOR_IOC_S_STREAM,&off);
        if(err!=ESP_OK) { camera_fail("stream-off",err); ok=false; }
        else camera_diag("stream-off");
    }
    const esp_err_t stop_err=started?esp_cam_ctlr_stop(controller):ESP_OK;
    bool dma_stopped=!started || stop_err==ESP_OK;
    if (!dma_stopped) {
        // Keep ISR metadata and DMA memory alive after an uncertain stop.
        // No further camera capture until reset; never free live DMA memory.
        g_camera_poisoned=true;
        ESP_LOGE(kLogTag,"CAMERA state=quarantined reason=dma-stop err=%s",esp_err_to_name(stop_err));
        camera_diag("dma-stop-quarantined");
        return false;
    }
    if(started) camera_diag("controller-stopped");
    if(enabled) {
        const esp_err_t err=esp_cam_ctlr_disable(controller);
        if(err!=ESP_OK) { camera_fail("controller-disable",err); ok=false; }
        else camera_diag("controller-disabled");
    }
    if(controller) {
        const esp_err_t err=esp_cam_ctlr_del(controller);
        if(err!=ESP_OK) { camera_fail("controller-delete",err); ok=false; }
        else camera_diag("controller-deleted");
    }
    if(sensor) {
        const esp_err_t err=esp_cam_sensor_del_dev(sensor);
        if(err!=ESP_OK) { camera_fail("sensor-delete",err); ok=false; }
        else camera_diag("sensor-deleted");
    }
    if(sccb) {
        const esp_err_t err=esp_sccb_del_i2c_io(sccb);
        if(err!=ESP_OK) { camera_fail("sccb-delete",err); ok=false; }
        else camera_diag("sccb-deleted");
    }
    if(g_camera_capture.completed) vQueueDelete(g_camera_capture.completed);
    g_camera_capture.completed=nullptr;
    if(ok) {
        const esp_err_t err=esp_cache_msync(g_camera_capture.buffer,kCameraBytes,ESP_CACHE_MSYNC_FLAG_DIR_M2C);
        if(err!=ESP_OK) { camera_fail("cache-sync",err); ok=false; }
        else camera_diag("cache-synced");
    }
    if(ok) { frame.data=g_camera_capture.buffer; frame.size=kCameraBytes; }
    else heap_caps_free(g_camera_capture.buffer);
    g_camera_capture.buffer=nullptr;
    g_camera_active.store(false);
    camera_diag(ok?"complete":"failed-clean");
    return ok;
}
}
