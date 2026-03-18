// builder.sce
// No compiled code in this toolbox.
TOOLBOX_DIR = get_absolute_file_path('builder.sce');
if isdef('tbx_builder_macros') then
    tbx_builder_macros(TOOLBOX_DIR);
else
    genlib('XcosAICompilerlib', TOOLBOX_DIR + 'macros/', %f, %t);
end
