from __future__ import annotations

from pathlib import Path


FIRMWARE_ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = FIRMWARE_ROOT / "main" / "kadence_voice_transport.h"
MAIN = FIRMWARE_ROOT / "main" / "main.cpp"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label} guard expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_transport() -> None:
    text = TRANSPORT.read_text(encoding="utf-8").replace("\r\n", "\n")
    changed = False

    enum_marker = "enum class WeatherIcon : uint8_t"
    if enum_marker not in text:
        text = replace_once(
            text,
            "class Service {\npublic:\n",
            "enum class WeatherIcon : uint8_t {\n"
            "    None = 0,\n"
            "    Clear,\n"
            "    Cloud,\n"
            "    Rain,\n"
            "    Snow,\n"
            "};\n\n"
            "class Service {\npublic:\n",
            "weather enum",
        )
        changed = True

    take_marker = "bool take_weather_icon(WeatherIcon& icon)"
    if take_marker not in text:
        anchor = (
            "    // Compatibility contract with the proven Beta UI state machine. In 2.0\n"
            "    // Alpha 1 this becomes ready only after STT + TTS + playback drain are done.\n"
        )
        block = (
            "    bool take_weather_icon(WeatherIcon& icon)\n"
            "    {\n"
            "        const uint8_t raw = weather_icon_requested_.exchange(\n"
            "            static_cast<uint8_t>(WeatherIcon::None));\n"
            "        if (raw == static_cast<uint8_t>(WeatherIcon::None)) {\n"
            "            return false;\n"
            "        }\n"
            "        icon = static_cast<WeatherIcon>(raw);\n"
            "        return true;\n"
            "    }\n\n"
        )
        text = replace_once(text, anchor, block + anchor, "weather take method")
        changed = True

    atomic_marker = "std::atomic<uint8_t> weather_icon_requested_"
    if atomic_marker not in text:
        text = replace_once(
            text,
            "    std::atomic<bool> server_endpoint_requested_{false};\n"
            "    std::atomic<bool> transcript_ready_{false};\n",
            "    std::atomic<bool> server_endpoint_requested_{false};\n"
            "    std::atomic<uint8_t> weather_icon_requested_{\n"
            "        static_cast<uint8_t>(WeatherIcon::None)};\n"
            "    std::atomic<bool> transcript_ready_{false};\n",
            "weather atomic",
        )
        changed = True

    parser_marker = 'std::strcmp(event->valuestring, "weather_icon") == 0'
    if parser_marker not in text:
        anchor = (
            "                // Unknown version-1 Kadence controls are deliberately ignored so\n"
            "                // future server features cannot accidentally alter Alpha motion\n"
            "                // or device state.\n"
        )
        block = (
            "                if (std::strcmp(event->valuestring, \"weather_icon\") == 0) {\n"
            "                    const cJSON* condition =\n"
            "                        cJSON_GetObjectItem(root, \"condition\");\n"
            "                    if (!cJSON_IsString(condition)) {\n"
            "                        mclog::tagInfo(\n"
            "                            kLogTag,\n"
            "                            \"ignored Kadence weather icon without condition\");\n"
            "                        return;\n"
            "                    }\n\n"
            "                    WeatherIcon icon = WeatherIcon::None;\n"
            "                    if (std::strcmp(condition->valuestring, \"clear\") == 0) {\n"
            "                        icon = WeatherIcon::Clear;\n"
            "                    } else if (std::strcmp(condition->valuestring, \"cloud\") == 0) {\n"
            "                        icon = WeatherIcon::Cloud;\n"
            "                    } else if (std::strcmp(condition->valuestring, \"rain\") == 0) {\n"
            "                        icon = WeatherIcon::Rain;\n"
            "                    } else if (std::strcmp(condition->valuestring, \"snow\") == 0) {\n"
            "                        icon = WeatherIcon::Snow;\n"
            "                    }\n\n"
            "                    if (icon == WeatherIcon::None) {\n"
            "                        mclog::tagInfo(\n"
            "                            kLogTag,\n"
            "                            \"ignored unsupported Kadence weather icon condition\");\n"
            "                        return;\n"
            "                    }\n\n"
            "                    weather_icon_requested_.store(\n"
            "                        static_cast<uint8_t>(icon));\n"
            "                    mclog::tagInfo(\n"
            "                        kLogTag,\n"
            "                        \"Kadence weather icon control received: {}\",\n"
            "                        condition->valuestring);\n"
            "                    return;\n"
            "                }\n\n"
        )
        text = replace_once(text, anchor, block + anchor, "weather control parser")
        changed = True

    required = (
        enum_marker,
        take_marker,
        atomic_marker,
        parser_marker,
        '"clear"',
        '"cloud"',
        '"rain"',
        '"snow"',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise RuntimeError(f"weather transport post-patch verification failed: {missing}")

    if changed:
        TRANSPORT.write_text(text, encoding="utf-8", newline="\n")
        print("Applied guarded M6 weather control overlay to kadence_voice_transport.h")
    else:
        print("M6 weather control overlay already applied")


def patch_main() -> None:
    text = MAIN.read_text(encoding="utf-8").replace("\r\n", "\n")
    changed = False

    ui_marker = "void initialise_weather_overlay()"
    if ui_marker not in text:
        anchor = (
            "bool g_beta_voice_processor_enabled = false;\n"
            "bool g_beta_processor_stop_scheduled = false;\n"
            "uint32_t g_beta_processor_stop_deadline_ms = 0;\n\n"
        )
        block = r'''lv_obj_t* g_weather_overlay = nullptr;
bool g_weather_overlay_visible = false;

lv_obj_t* create_weather_shape(
    lv_obj_t* parent,
    int x,
    int y,
    int width,
    int height,
    uint32_t colour,
    int radius)
{
    lv_obj_t* shape = lv_obj_create(parent);
    lv_obj_remove_flag(shape, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_pos(shape, x, y);
    lv_obj_set_size(shape, width, height);
    lv_obj_set_style_pad_all(shape, 0, LV_PART_MAIN);
    lv_obj_set_style_border_width(shape, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(shape, radius, LV_PART_MAIN);
    lv_obj_set_style_bg_color(shape, lv_color_hex(colour), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(shape, LV_OPA_COVER, LV_PART_MAIN);
    return shape;
}

void initialise_weather_overlay()
{
    LvglLockGuard lock;
    g_weather_overlay = lv_obj_create(lv_screen_active());
    lv_obj_remove_flag(g_weather_overlay, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_pos(g_weather_overlay, 0, 0);
    lv_obj_set_size(g_weather_overlay, 320, 240);
    lv_obj_set_style_pad_all(g_weather_overlay, 0, LV_PART_MAIN);
    lv_obj_set_style_border_width(g_weather_overlay, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(g_weather_overlay, 0, LV_PART_MAIN);
    lv_obj_set_style_bg_color(g_weather_overlay, lv_color_hex(0x000000), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(g_weather_overlay, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_add_flag(g_weather_overlay, LV_OBJ_FLAG_HIDDEN);
}

void draw_weather_cloud(lv_obj_t* parent)
{
    constexpr uint32_t cloud = 0xC8D0D8;
    create_weather_shape(parent, 90, 106, 140, 48, cloud, 24);
    create_weather_shape(parent, 105, 82, 64, 64, cloud, LV_RADIUS_CIRCLE);
    create_weather_shape(parent, 145, 72, 76, 76, cloud, LV_RADIUS_CIRCLE);
}

void show_weather_icon(kadence_voice_transport::WeatherIcon icon)
{
    if (g_weather_overlay == nullptr || icon == kadence_voice_transport::WeatherIcon::None) {
        return;
    }

    LvglLockGuard lock;
    lv_obj_clean(g_weather_overlay);
    lv_obj_set_style_bg_color(g_weather_overlay, lv_color_hex(0x000000), LV_PART_MAIN);

    switch (icon) {
        case kadence_voice_transport::WeatherIcon::Clear: {
            constexpr uint32_t sun = 0xFFD84A;
            create_weather_shape(g_weather_overlay, 120, 80, 80, 80, sun, LV_RADIUS_CIRCLE);
            create_weather_shape(g_weather_overlay, 154, 48, 12, 24, sun, 6);
            create_weather_shape(g_weather_overlay, 154, 168, 12, 24, sun, 6);
            create_weather_shape(g_weather_overlay, 88, 114, 24, 12, sun, 6);
            create_weather_shape(g_weather_overlay, 208, 114, 24, 12, sun, 6);
            create_weather_shape(g_weather_overlay, 103, 62, 14, 14, sun, 7);
            create_weather_shape(g_weather_overlay, 203, 62, 14, 14, sun, 7);
            create_weather_shape(g_weather_overlay, 103, 164, 14, 14, sun, 7);
            create_weather_shape(g_weather_overlay, 203, 164, 14, 14, sun, 7);
            break;
        }
        case kadence_voice_transport::WeatherIcon::Cloud:
            draw_weather_cloud(g_weather_overlay);
            break;
        case kadence_voice_transport::WeatherIcon::Rain:
            draw_weather_cloud(g_weather_overlay);
            create_weather_shape(g_weather_overlay, 108, 166, 10, 30, 0x43C6FF, 5);
            create_weather_shape(g_weather_overlay, 144, 174, 10, 30, 0x43C6FF, 5);
            create_weather_shape(g_weather_overlay, 180, 166, 10, 30, 0x43C6FF, 5);
            create_weather_shape(g_weather_overlay, 216, 174, 10, 30, 0x43C6FF, 5);
            break;
        case kadence_voice_transport::WeatherIcon::Snow:
            draw_weather_cloud(g_weather_overlay);
            create_weather_shape(g_weather_overlay, 112, 174, 12, 12, 0xFFFFFF, LV_RADIUS_CIRCLE);
            create_weather_shape(g_weather_overlay, 148, 190, 12, 12, 0xFFFFFF, LV_RADIUS_CIRCLE);
            create_weather_shape(g_weather_overlay, 184, 174, 12, 12, 0xFFFFFF, LV_RADIUS_CIRCLE);
            create_weather_shape(g_weather_overlay, 220, 190, 12, 12, 0xFFFFFF, LV_RADIUS_CIRCLE);
            break;
        case kadence_voice_transport::WeatherIcon::None:
        default:
            return;
    }

    lv_obj_remove_flag(g_weather_overlay, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(g_weather_overlay);
    g_weather_overlay_visible = true;
}

void hide_weather_overlay()
{
    if (g_weather_overlay == nullptr || !g_weather_overlay_visible) {
        return;
    }
    LvglLockGuard lock;
    lv_obj_add_flag(g_weather_overlay, LV_OBJ_FLAG_HIDDEN);
    g_weather_overlay_visible = false;
}

'''
        text = replace_once(text, anchor, anchor + block, "weather UI helpers")
        changed = True

    poll_marker = "g_voice_transport.take_weather_icon(weather_icon)"
    if poll_marker not in text:
        anchor = "    g_voice_transport.update();\n    service_beta_processor_stop(now);\n"
        block = (
            "    g_voice_transport.update();\n"
            "    service_beta_processor_stop(now);\n\n"
            "    kadence_voice_transport::WeatherIcon weather_icon =\n"
            "        kadence_voice_transport::WeatherIcon::None;\n"
            "    if (g_voice_transport.take_weather_icon(weather_icon)) {\n"
            "        show_weather_icon(weather_icon);\n"
            "    }\n"
        )
        text = replace_once(text, anchor, block, "weather event poll")
        changed = True

    init_marker = "    initialise_weather_overlay();\n"
    if init_marker not in text:
        text = replace_once(
            text,
            "    initialise_eye_surface();\n    initialise_head_touch_toggle();\n",
            "    initialise_eye_surface();\n"
            "    initialise_weather_overlay();\n"
            "    initialise_head_touch_toggle();\n",
            "weather overlay init",
        )
        changed = True

    hide_marker = "hide_weather_overlay();\n        update_eye_state(now);"
    if hide_marker not in text:
        text = replace_once(
            text,
            "        update_voice_ui_alpha(now);\n"
            "        update_eye_state(now);\n",
            "        update_voice_ui_alpha(now);\n"
            "        if (g_voice_ui_runtime.state == VoiceUiState::Idle ||\n"
            "            g_voice_ui_runtime.state == VoiceUiState::Error) {\n"
            "            hide_weather_overlay();\n"
            "        }\n"
            "        update_eye_state(now);\n",
            "weather overlay reset",
        )
        changed = True

    required = (
        ui_marker,
        poll_marker,
        init_marker.strip(),
        "hide_weather_overlay();",
        "WeatherIcon::Clear",
        "WeatherIcon::Cloud",
        "WeatherIcon::Rain",
        "WeatherIcon::Snow",
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise RuntimeError(f"weather UI post-patch verification failed: {missing}")

    if changed:
        MAIN.write_text(text, encoding="utf-8", newline="\n")
        print("Applied guarded M6 weather UI overlay to main.cpp")
    else:
        print("M6 weather UI overlay already applied")


def main() -> None:
    patch_transport()
    patch_main()
    print("Kadence M6 firmware weather overlay: PASS")


if __name__ == "__main__":
    main()
