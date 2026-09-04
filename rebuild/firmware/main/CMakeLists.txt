idf_component_register(
    SRCS "probe16.cpp"
    INCLUDE_DIRS "."
    PRIV_REQUIRES esp_app_format esp_driver_i2c esp_driver_i2s esp_driver_spi esp_driver_uart esp_lcd esp_timer esp_codec_dev json nvs_flash
)
