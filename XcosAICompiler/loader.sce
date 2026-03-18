// loader.sce
TOOLBOX_DIR = get_absolute_file_path("loader.sce");
global XCOSAI_MODULE_ROOT;
XCOSAI_MODULE_ROOT = TOOLBOX_DIR;

mprintf("[XcosAICompiler] Loading macros...\n");
// Clear existing functions to force re-loading from .sci source
clear check_api_key launch_ai_compiler_gui run_correction_loop xcosai_poll_loop;

// Brute force exec to ensure global visibility in Scilab 2026
exec(TOOLBOX_DIR + "macros/check_api_key.sci");
exec(TOOLBOX_DIR + "macros/launch_ai_compiler_gui.sci");
exec(TOOLBOX_DIR + "macros/run_correction_loop.sci");
exec(TOOLBOX_DIR + "macros/xcosai_poll_loop.sci");

exec(TOOLBOX_DIR + "etc/module.start");
