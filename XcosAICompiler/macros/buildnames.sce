// buildnames.sce
files = ['launch_ai_compiler_gui';
         'check_api_key';
         'run_correction_loop';
         'xcosai_poll_loop'];
tbx_build_macros('XcosAICompiler', get_absolute_file_path('buildnames.sce'));
