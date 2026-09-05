cmake_minimum_required(VERSION 3.16)

set(PROJECT_VER "0.19.0")
set(SDKCONFIG "${CMAKE_BINARY_DIR}/kadence-sdkconfig")
set(SDKCONFIG_DEFAULTS "${CMAKE_CURRENT_LIST_DIR}/sdkconfig.defaults")

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(kade-body-probe)
