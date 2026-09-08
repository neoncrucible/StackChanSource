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
    if (g_camera_poisoned || voice_cancel_is_requested()) return false;
    g_camera_active.store(true);
    esp_sccb_io_handle_t sccb=nullptr;
    esp_cam_sensor_device_t* sensor=nullptr;
    esp_cam_ctlr_handle_t controller=nullptr;
    bool enabled=false,started=false,streaming=false;
    g_camera_capture.completed=xQueueCreate(1,sizeof(size_t));
    g_camera_capture.buffer=static_cast<uint8_t*>(heap_caps_aligned_alloc(64,kCameraBytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
    bool ok=[&]() {
        if (!g_camera_capture.completed || !g_camera_capture.buffer) return false;
        sccb_i2c_config_t bus{};
        bus.dev_addr_length=I2C_ADDR_BIT_LEN_7; bus.device_address=GC0308_SCCB_ADDR; bus.scl_speed_hz=100000;
        if (sccb_new_i2c_io(g_control.i2c_bus,&bus,&sccb)!=ESP_OK) return false;
        esp_cam_sensor_config_t sensor_config{};
        sensor_config.sccb_handle=sccb; sensor_config.reset_pin=GPIO_NUM_NC; sensor_config.pwdn_pin=GPIO_NUM_NC; sensor_config.xclk_pin=GPIO_NUM_NC;
        sensor=gc0308_detect(&sensor_config);
        if (!sensor || voice_cancel_is_requested() || esp_cam_sensor_set_format(sensor,nullptr)!=ESP_OK) return false;
        esp_cam_sensor_format_t format{};
        if(esp_cam_sensor_get_format(sensor,&format)!=ESP_OK || format.width!=320 || format.height!=240 || format.format!=ESP_CAM_SENSOR_PIXFORMAT_RGB565) return false;
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
        if(esp_cam_new_dvp_ctlr(&config,&controller)!=ESP_OK) return false;
        esp_cam_ctlr_evt_cbs_t callbacks{};
        callbacks.on_get_new_trans=camera_get_frame; callbacks.on_trans_finished=camera_frame_done;
        if(esp_cam_ctlr_register_event_callbacks(controller,&callbacks,nullptr)!=ESP_OK) return false;
        if(esp_cam_ctlr_enable(controller)!=ESP_OK) return false;
        enabled=true;
        if(esp_cam_ctlr_start(controller)!=ESP_OK) return false;
        started=true;
        int on=1;
        if(esp_cam_sensor_ioctl(sensor,ESP_CAM_SENSOR_IOC_S_STREAM,&on)!=ESP_OK) return false;
        streaming=true;
        for(int i=0;i<12;++i) { if(voice_cancel_is_requested()) return false; vTaskDelay(pdMS_TO_TICKS(50)); }
        g_camera_capture.wanted.store(true);
        size_t received=0;
        for(int i=0;i<30;++i) {
            if(voice_cancel_is_requested()) return false;
            if(xQueueReceive(g_camera_capture.completed,&received,pdMS_TO_TICKS(50))==pdTRUE) return received==kCameraBytes;
        }
        return false;
    }();
    g_camera_capture.wanted.store(false);
    int off=0;
    if(streaming && esp_cam_sensor_ioctl(sensor,ESP_CAM_SENSOR_IOC_S_STREAM,&off)!=ESP_OK) ok=false;
    bool dma_stopped=!started || esp_cam_ctlr_stop(controller)==ESP_OK;
    if (!dma_stopped) {
        // Keep ISR metadata and DMA memory alive after an uncertain stop.
        // No further camera capture until reset; never free live DMA memory.
        g_camera_poisoned=true;
        ESP_LOGE(kLogTag,"CAMERA state=quarantined reason=dma-stop");
        return false;
    }
    if(enabled && esp_cam_ctlr_disable(controller)!=ESP_OK) ok=false;
    if(controller && esp_cam_ctlr_del(controller)!=ESP_OK) ok=false;
    if(sensor && esp_cam_sensor_del_dev(sensor)!=ESP_OK) ok=false;
    if(sccb && esp_sccb_del_i2c_io(sccb)!=ESP_OK) ok=false;
    if(g_camera_capture.completed) vQueueDelete(g_camera_capture.completed);
    g_camera_capture.completed=nullptr;
    if(ok) {
        if(esp_cache_msync(g_camera_capture.buffer,kCameraBytes,ESP_CACHE_MSYNC_FLAG_DIR_M2C)!=ESP_OK) ok=false;
    }
    if(ok) { frame.data=g_camera_capture.buffer; frame.size=kCameraBytes; }
    else heap_caps_free(g_camera_capture.buffer);
    g_camera_capture.buffer=nullptr;
    g_camera_active.store(false);
    return ok;
}
}
