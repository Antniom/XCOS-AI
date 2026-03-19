function launch_ai_compiler_gui()
    // launch_ai_compiler_gui.sci
    // REPLACED: Now launches the Web Dashboard instead of the legacy Java GUI.
    
    global XCOSAI_MODULE_ROOT;
    
    // 1. Resolve paths
    if getos() == 'Windows' then 
        py = 'python';
        start_browser = 'start http://127.0.0.1:8000';
    else 
        py = 'python3';
        start_browser = 'open http://127.0.0.1:8000';
    end
    
    server_script = XCOSAI_MODULE_ROOT + "/../xcosgen/server/main.py";
    dq = ascii(34);
    // Use ascii(39) for single quotes — Scilab treats ' inside "..." as transpose
    // operator and throws "Heterogeneous string" errors. Never write ' inside "".
    sq = ascii(39);
    
    mprintf('[XcosAI] Performing pre-launch cleanup...\n');
    if getos() == "Windows" then
        // Kill old Python backend by command line content.
        // Previous approach used /FI WINDOWTITLE but the server is launched with
        // /B (no window), so it has no window title and was never killed.
        // wmic process where "commandline like '%main.py%'" delete is reliable.
        mprintf('[XcosAI] Killing old Python backend (if any)...\n');
        kill_py_cmd = "wmic process where " + dq + "commandline like " + sq + "%main.py%" + sq + dq + " delete >nul 2>&1";
        host(kill_py_cmd);
        
        // Kill ghost Scilab processes (protect current PID)
        curr_pid = string(getpid());
        mprintf("[XcosAI] Clearing ghost Scilab pollers (Protecting PID %s)...\n", curr_pid);
        
        kill_scilab_cmd = "powershell -NoProfile -NonInteractive -Command " + dq + ..
                   "Get-Process scilab-bin,WScilex -ErrorAction SilentlyContinue | " + ..
                   "Where-Object { $_.Id -ne " + curr_pid + " } | " + ..
                   "Stop-Process -Force -ErrorAction SilentlyContinue" + dq;
        host(kill_scilab_cmd);
        
        // Clear port 8000 with a hard 5-second timeout so host() can never block
        // indefinitely (e.g. if the owning process is elevated and resists kill).
        mprintf("[XcosAI] Clearing port 8000...\n");
        clear_port_cmd = "powershell -NoProfile -NonInteractive -Command " + dq + ..
            "$j = Start-Job { " + ..
                "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | " + ..
                "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } " + ..
            "}; " + ..
            "Wait-Job $j -Timeout 5 | Out-Null; " + ..
            "Remove-Job $j -Force -ErrorAction SilentlyContinue" + dq;
        host(clear_port_cmd);
        mprintf("[XcosAI] Port cleanup done.\n");
    else
        host("pkill -f " + dq + server_script + dq);
    end
    
    mprintf('[XcosAI] Launching Python Backend...\n');
    if getos() == "Windows" then
        host("start " + dq + "XcosAI_Backend" + dq + " /B " + py + " " + dq + server_script + dq);
    else
        host(py + " " + dq + server_script + dq + " &");
    end
    
    // Wait a moment for server to warm up
    sleep(2000);
    
    mprintf('[XcosAI] Opening Web Dashboard...\n');
    host(start_browser);
    
    mprintf('[XcosAI] Starting Validation Poll Loop...\n');
    mprintf('[XcosAI] Scilab will now check for diagrams generated in the Web Dashboard.\n');
    
    // Start the polling loop
    xcosai_poll_loop();
    
endfunction
