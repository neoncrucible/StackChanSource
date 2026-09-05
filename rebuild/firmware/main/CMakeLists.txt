idf_component_register(
    SRCS "probe21.cpp"
    INCLUDE_DIRS "."
    PRIV_REQUIRES esp_app_format esp_driver_i2c esp_driver_i2s esp_driver_spi esp_driver_uart esp_event esp_lcd esp_netif esp_psram esp_timer esp_wifi esp_codec_dev json lwip nvs_flash
)
