idf_component_register(
    SRCS "probe6_warm.cpp"
    INCLUDE_DIRS "."
    PRIV_REQUIRES esp_app_format esp_driver_i2c esp_driver_uart esp_timer nvs_flash
)
