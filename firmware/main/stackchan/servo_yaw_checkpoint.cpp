#include "../servo_yaw_checkpoint.h"

extern "C" void kade_run_servo_yaw_checkpoint()
{
    kade_servo_checkpoint::run_once();
}
