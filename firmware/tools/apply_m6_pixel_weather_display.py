from __future__ import annotations

from pathlib import Path


FIRMWARE_ROOT = Path(__file__).resolve().parents[1]
MAIN = FIRMWARE_ROOT / "main" / "main.cpp"
PIXEL_MARKER = "// Kadence M6 pixel weather overlay v1"
START_MARKER = "lv_obj_t* g_weather_overlay = nullptr;\n"
END_MARKER = "void set_beta_voice_processor("


PIXEL_BLOCK = r'''// Kadence M6 pixel weather overlay v1
lv_obj_t* g_weather_overlay = nullptr;
bool g_weather_overlay_visible = false;

lv_obj_t* create_weather_pixel(
    lv_obj_t* parent,
    int x,
    int y,
    int width,
    int height,
    uint32_t colour)
{
    lv_obj_t* pixel = lv_obj_create(parent);
    lv_obj_remove_flag(pixel, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_pos(pixel, x, y);
    lv_obj_set_size(pixel, width, height);
    lv_obj_set_style_pad_all(pixel, 0, LV_PART_MAIN);
    lv_obj_set_style_border_width(pixel, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(pixel, 0, LV_PART_MAIN);
    lv_obj_set_style_bg_color(pixel, lv_color_hex(colour), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(pixel, LV_OPA_COVER, LV_PART_MAIN);
    return pixel;
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

void draw_pixel_cloud(lv_obj_t* parent)
{
    constexpr uint32_t cloud = 0xC8D0D8;
    create_weather_pixel(parent, 96, 112, 128, 40, cloud);
    create_weather_pixel(parent, 80, 128, 32, 24, cloud);
    create_weather_pixel(parent, 208, 120, 32, 32, cloud);
    create_weather_pixel(parent, 112, 96, 32, 16, cloud);
    create_weather_pixel(parent, 128, 80, 48, 32, cloud);
    create_weather_pixel(parent, 176, 96, 32, 16, cloud);
}

void draw_pixel_snowflake(lv_obj_t* parent, int x, int y)
{
    constexpr uint32_t snow = 0xFFFFFF;
    create_weather_pixel(parent, x + 8, y, 8, 24, snow);
    create_weather_pixel(parent, x, y + 8, 24, 8, snow);
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
            create_weather_pixel(g_weather_overlay, 128, 88, 64, 64, sun);
            create_weather_pixel(g_weather_overlay, 152, 48, 16, 24, sun);
            create_weather_pixel(g_weather_overlay, 152, 168, 16, 24, sun);
            create_weather_pixel(g_weather_overlay, 88, 112, 24, 16, sun);
            create_weather_pixel(g_weather_overlay, 208, 112, 24, 16, sun);
            create_weather_pixel(g_weather_overlay, 104, 64, 16, 16, sun);
            create_weather_pixel(g_weather_overlay, 200, 64, 16, 16, sun);
            create_weather_pixel(g_weather_overlay, 104, 160, 16, 16, sun);
            create_weather_pixel(g_weather_overlay, 200, 160, 16, 16, sun);
            break;
        }
        case kadence_voice_transport::WeatherIcon::Cloud:
            draw_pixel_cloud(g_weather_overlay);
            break;
        case kadence_voice_transport::WeatherIcon::Rain:
            draw_pixel_cloud(g_weather_overlay);
            create_weather_pixel(g_weather_overlay, 104, 168, 8, 24, 0x43C6FF);
            create_weather_pixel(g_weather_overlay, 144, 184, 8, 24, 0x43C6FF);
            create_weather_pixel(g_weather_overlay, 184, 168, 8, 24, 0x43C6FF);
            create_weather_pixel(g_weather_overlay, 224, 184, 8, 24, 0x43C6FF);
            break;
        case kadence_voice_transport::WeatherIcon::Snow:
            draw_pixel_cloud(g_weather_overlay);
            draw_pixel_snowflake(g_weather_overlay, 96, 168);
            draw_pixel_snowflake(g_weather_overlay, 144, 184);
            draw_pixel_snowflake(g_weather_overlay, 192, 168);
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


def main() -> None:
    text = MAIN.read_text(encoding="utf-8").replace("\r\n", "\n")

    if PIXEL_MARKER in text:
        print("Kadence M6 pixel weather display already applied")
        return

    start = text.find(START_MARKER)
    if start < 0 or "void initialise_weather_overlay()" not in text:
        raise RuntimeError(
            "M6 base weather overlay was not present before pixel migration"
        )

    end = text.find(END_MARKER, start)
    if end < 0:
        raise RuntimeError("M6 pixel weather migration end anchor was not found")

    text = text[:start] + PIXEL_BLOCK + text[end:]

    required = (
        PIXEL_MARKER,
        "create_weather_pixel(",
        "draw_pixel_cloud(",
        "draw_pixel_snowflake(",
        "WeatherIcon::Clear",
        "WeatherIcon::Cloud",
        "WeatherIcon::Rain",
        "WeatherIcon::Snow",
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise RuntimeError(f"M6 pixel weather verification failed: {missing}")

    MAIN.write_text(text, encoding="utf-8", newline="\n")
    print("Kadence M6 pixel weather display migration: PASS")


if __name__ == "__main__":
    main()
