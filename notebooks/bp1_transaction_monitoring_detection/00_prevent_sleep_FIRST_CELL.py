# ============================================================================
# Run this as the FIRST cell, before the main notebook cell, on every long run
# (NB3's Stage A/B and NB2's feature engineering are both multi-hour jobs).
#
# Tells Windows "don't sleep while this process is alive" using the standard,
# documented Win32 SetThreadExecutionState API (kernel32.dll). This is a
# backup to the OS power-setting change (Settings > Power & Battery > Screen
# and sleep > Never) -- do both, since a Windows Update or group policy can
# silently reset the power-plan setting, but this in-process flag can't be
# reset by anything short of the process itself exiting.
#
# Real, disclosed limitation: this only stops SYSTEM SLEEP. It does nothing
# for a lid-close on a laptop configured to sleep-on-lid-close regardless of
# running processes -- if you physically close the lid, set Windows' own
# "When I close the lid" power setting to "Do nothing" as well, or leave the
# lid open for the duration of a long run.
# ============================================================================
import ctypes
import atexit

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

def _prevent_system_sleep():
    result = ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    if result == 0:
        print("WARNING: SetThreadExecutionState call failed (returned 0) -- sleep prevention may "
              "not be active. Rely on the OS power-setting change as the primary safeguard.")
    else:
        print("Sleep prevention ACTIVE for this kernel process -- Windows will not suspend the "
              "system while this Jupyter kernel is running (display may still sleep separately; "
              "that does not affect the running computation).")

def _restore_normal_sleep():
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    print("Sleep prevention released -- normal Windows power management resumed.")

_prevent_system_sleep()
atexit.register(_restore_normal_sleep)  # best-effort cleanup if the kernel exits cleanly
