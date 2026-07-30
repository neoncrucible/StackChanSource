/*
 * Project Kadence Alpha 1 response entry point.
 *
 * The included volume wrapper contains the proven response implementation and
 * its historical constructor. Suppress included xTaskCreate calls so only the
 * single final constructor below launches the response service.
 */

#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#undef xTaskCreate
#define xTaskCreate(...) pdPASS
#include "kadence_voice_response_volume.inc"
#undef xTaskCreate

extern "C" void __attribute__((constructor)) start_kadence_alpha_response_service()
{
    const BaseType_t created = xTaskCreatePinnedToCore(
        kadence_voice_response::response_task,
        "kade_voice_rx",
        8192,
        nullptr,
        4,
        nullptr,
        tskNO_AFFINITY);
    if (created != pdPASS) {
        mclog::tagError(
            "KADENCE-VOICE-RX",
            "failed to create robot speaker response task");
    }
}
