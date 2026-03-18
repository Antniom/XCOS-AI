function xcosai_poll_loop()
    // xcosai_poll_loop.sci
    // Polls the Python server for new Xcos diagrams to validate.
    
    global XCOSAI_SERVER_PORT;
    if ~isdef('XCOSAI_SERVER_PORT') | isempty(XCOSAI_SERVER_PORT) then 
        XCOSAI_SERVER_PORT = 8000; 
    end
    
    POLL_MS = 1000;
    
    // Seed rand using current time to ensure unique LoopID on restart
    // Scilab 2026 rand() is deterministic without seeding.
    try
        rand('seed', getdate('s'));
    catch
        // Ignore seeding errors
    end
    
    LoopID = floor(rand()*10000);
    
    // Randomized initial delay (0-500ms) to stagger multiple ghost start-ups
    sleep(floor(rand()*500));
    
    disp('[XcosAI][' + string(LoopID) + '] Starting poll loop on port ' + string(XCOSAI_SERVER_PORT) + '...');
    disp('[XcosAI][' + string(LoopID) + '] Press Ctrl+C in Scilab console to stop.');
    
    global XCOSAI_POLLING_ACTIVE;
    XCOSAI_POLLING_ACTIVE = %t;
    
    url_base = 'http://127.0.0.1:' + string(XCOSAI_SERVER_PORT);
    startup_phase_end = getdate('s') + 10; // Ignore connection errors for first 10s
    
    while XCOSAI_POLLING_ACTIVE
        try
            resp = [];
            status = 0;
            try
                // PASS LoopID to backend for traceability
                [resp, status] = http_get(url_base + '/task?loop_id=' + string(LoopID));
            catch
                if getdate('s') < startup_phase_end then
                    // Silently wait during startup
                else
                    [err_msg, err_id] = lasterror();
                    disp('[XcosAI][' + string(LoopID) + '] Connection Error [' + string(err_id) + ']: ' + string(err_msg));
                    disp('[XcosAI][' + string(LoopID) + '] Retrying in 5s...');
                    sleep(4000); 
                end
                sleep(1000);
                continue;
            end
            
            if status == 200 then
                if isempty(resp) then continue; end
                
                // 1. Resolve response structure
                task = [];
                if isstruct(resp) then
                    task = resp;
                else
                    try
                        task = fromJSON(resp);
                    catch
                        disp('[XcosAI][' + string(LoopID) + '] JSON Parse Fail: ' + string(resp));
                        continue;
                    end
                end
                
                if isstruct(task) & isfield(task, 'status') then
                    if task.status == 'busy' then
                        // Another poller is master. 
                        // If it's another session, we just wait silently.
                        sleep(2000);
                        continue;
                    end

                    if task.status == 'pending' then
                        disp('[XcosAI][' + string(LoopID) + '] TASK RECEIVED: ' + string(task.task_id));
                        
                        task_id = ''; zcos_path = '';
                        try
                            task_id = task.task_id;
                            zcos_path = task.zcos_path;
                        catch
                            disp('[XcosAI][' + string(LoopID) + '] Error accessing task fields.');
                            continue;
                        end
                        
                        disp('[XcosAI][' + string(LoopID) + '] Target path: ' + string(zcos_path));
                    
                        // Verification Logic
                        success = %f;
                        err_msg = '';
                        
                        try
                            disp('[XcosAI][' + string(LoopID) + '] Loading libraries...');
                            loadXcosLibs();
                            
                            disp('[XcosAI][' + string(LoopID) + '] Importing diagram...');
                            importXcosDiagram(zcos_path);
                            
                            disp('[XcosAI][' + string(LoopID) + '] Starting simulation (nw mode)...');
                            // Scilab 2026 scicos_simulate requirements:
                            // 1: diagram (scs_m), 2: Info (list), 3: updated_vars (struct/string)
                            scicos_simulate(scs_m, list(), 'nw');
                            
                            success = %t;
                            disp('[XcosAI][' + string(LoopID) + '] Simulation COMPLETED.');
                        catch
                            [err_msg, err_id] = lasterror();
                            disp('[XcosAI][' + string(LoopID) + '] VERIFICATION ERROR [' + string(err_id) + ']: ' + string(err_msg));
                        end
                        
                        // 5. Send Result
                        disp('[XcosAI][' + string(LoopID) + '] Posting results...');
                        res_payload = struct('task_id', task_id, 'success', success, 'error', err_msg);
                        // Pass struct directly so Scilab adds 'application/json' headers automatically
                        [r, s] = http_post(url_base + '/result', res_payload);
                        disp('[XcosAI][' + string(LoopID) + '] Result posted (Status: ' + string(s) + ')');
                    end
                end
            else
                disp('[XcosAI][' + string(LoopID) + '] Server HTTP Error: ' + string(status));
                sleep(2000);
            end
        catch
            disp('[XcosAI][' + string(LoopID) + '] LOOP CRASH: ' + string(lasterror()));
            sleep(2000);
        end
        
        sleep(POLL_MS);
    end
    
    disp('[XcosAI][' + string(LoopID) + '] Polling loop stopped.');
endfunction
