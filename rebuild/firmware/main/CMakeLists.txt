idf_component_register(
    SRCS "main.cpp"
    INCLUDE_DIRS "."
    PRIV_REQUIRES esp_app_format esp_driver_i2c esp_driver_spi esp_lcd esp_lcd_ili9341
)
