function run_correction_loop(model_name, prompt, ref_files, base_xcos, hf, module_root)
// run_correction_loop.sci
// Logic for calling Python backend and correcting errors.

    job_file = TMPDIR + '/xcosai_job.json';
    result_file = TMPDIR + '/xcosai_result.json';
    output_xcos = TMPDIR + '/xcosai_output.zcos';

    if getos() == 'Windows' then py = 'python';
    else py = 'python3'; end
    
    agent_path = module_root + '/src/python/gemini_xcos_agent.py';
    py_cmd = py + ' "' + agent_path + '" --job "' + job_file + '"';

    function s_esc = json_escape(s)
        s_esc = strsubst(s, ascii(92), ascii(92)+ascii(92)); // \ -> \\
        s_esc = strsubst(s_esc, ascii(34), ascii(92)+ascii(34)); // " -> \"
        s_esc = strsubst(s_esc, ascii(10), "\n");
        s_esc = strsubst(s_esc, ascii(13), "\r");
        s_esc = strsubst(s_esc, ascii(9),  "\t");
    endfunction

    function write_job_json(job_file, mode, model, prompt, ref_files, base_xcos, error_log, faulty_xml, output_path)
        json_str = '{';
        json_str = json_str + '""mode"": ""' + mode + '"",';
        json_str = json_str + '""model"": ""' + model + '"",';
        json_str = json_str + '""prompt"": ""' + json_escape(prompt) + '"",';
        
        ref_files_str = '[';
        for i = 1:length(ref_files)
            ref_files_str = ref_files_str + '""' + json_escape(ref_files(i)) + '""';
            if i < length(ref_files) then ref_files_str = ref_files_str + ','; end
        end
        ref_files_str = ref_files_str + ']';
        
        json_str = json_str + '""ref_files"": ' + ref_files_str + ',';
        json_str = json_str + '""base_xcos"": ""' + json_escape(base_xcos) + '"",';
        json_str = json_str + '""error_log"": ""' + json_escape(error_log) + '"",';
        json_str = json_str + '""faulty_xml"": ""' + json_escape(faulty_xml) + '"",';
        json_str = json_str + '""output_xcos_path"": ""' + json_escape(output_path) + '""';
        json_str = json_str + '}';
        
        fid = mopen(job_file, 'w');
        mputl(json_str, fid);
        mclose(fid);
    endfunction

    function result = read_result_json(result_file)
        if ~isfile(result_file) then
            result = struct('success', %f, 'error', 'Result file not found');
            return;
        end
        fid = mopen(result_file, 'r');
        txt = strcat(mgetl(fid, -1), '');
        mclose(fid);
        
        result = struct();
        result.success = ~isempty(grep(txt, '""success"": true'));
        
        err_idx = strindex(txt, '""error"": ""');
        if ~isempty(err_idx) then
            err_rest = part(txt, err_idx(1)+11:length(txt));
            err_end = strindex(err_rest, '""');
            result.error = part(err_rest, 1:err_end(1)-1);
        else
            result.error = '';
        end
        
        // Batch info parsing (simplified)
        result.batch_info = struct('total_batches', 0, 'files_processed', 0, 'truncation_recoveries', 0);
        b_idx = strindex(txt, '""total_batches"": ');
        if ~isempty(b_idx) then
            val_rest = part(txt, b_idx(1)+17:length(txt));
            val_end = strindex(val_rest, ',');
            result.batch_info.total_batches = evstr(part(val_rest, 1:val_end(1)-1));
        end
        // ... similar for other fields
    endfunction

    success = %f;
    last_error = '';
    faulty_xml = '';
    iteration = 0;

    log_msg(hf, "Sending generation request...");
    write_job_json(job_file, "generate", model_name, prompt, ref_files, base_xcos, "", "", output_xcos);
    [ret, out] = host(py_cmd);
    result = read_result_json(result_file);

    if ~result.success then
        log_msg(hf, "ERROR from API: " + result.error);
        return;
    end

    log_msg(hf, "API call complete. Starting simulation loop...");

    while iteration < 5 & ~success
        iteration = iteration + 1;
        log_msg(hf, "Iteration " + string(iteration) + ": Loading diagram...");
        
        try
            loadXcosLibs();
            loadScicos();
            importXcosDiagram(output_xcos);
            Info = scicos_simulate(scs_m, list(), [], "nw");
            success = %t;
            log_msg(hf, "v Simulation successful on iteration " + string(iteration));
        catch
            last_error = lasterror();
            log_msg(hf, "x Error: " + last_error);
            
            if iteration < 5 then
                fid = mopen(output_xcos, "r");
                flines = mgetl(fid, -1);
                mclose(fid);
                faulty_xml = strcat(flines, ascii(10));
                
                log_msg(hf, "Requesting correction from API...");
                write_job_json(job_file, "correct", model_name, prompt, [], "", last_error, faulty_xml, output_xcos);
                [ret, out] = host(py_cmd);
                result = read_result_json(result_file);
                if ~result.success then
                    log_msg(hf, "ERROR from API during correction: " + result.error);
                    iteration = 5;
                end
            end
        end
    end

    if ~success then
        log_msg(hf, "x Failed after 5 iterations. Last error: " + last_error);
    else
        log_msg(hf, "v Process complete. Diagram ready.");
        answer = messagebox("Diagram generated successfully! Open in Xcos?", "Success", "question", ["Open", "Close"]);
        if answer == 1 then xcos(output_xcos); end
    end
endfunction
