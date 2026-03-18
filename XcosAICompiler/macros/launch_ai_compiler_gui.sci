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
    
    mprintf('[XcosAI] Performing pre-launch cleanup...\n');
    if getos() == "Windows" then
        // Kill previous Python backend instances
        host("taskkill /F /IM python.exe /FI " + dq + "COMMANDLINE eq *main.py*" + dq + " >nul 2>&1");
        
        // Kill Scilab ghosts (processes with no visible window holding onto the loop)
        // 2. Kill ghost Scilab processes (polls from old sessions)
        // We target WScilex (GUI) and scilab-bin (headless/backend)
        // We protect the CURRENT Scilab process to avoid self-termination
        curr_pid = string(getpid());
        mprintf("[XcosAI] Clearing ghost Scilab pollers (Protecting PID %s)...\n", curr_pid);
        
        // PowerShell command to kill all other Scilab instances
        kill_cmd = "powershell -Command ""Get-Process scilab-bin, WScilex -ErrorAction SilentlyContinue | " + ..
                   "Where-Object { $_.Id -ne " + curr_pid + " } | " + ..
                   "Stop-Process -Force -ErrorAction SilentlyContinue""";
        host(kill_cmd);
        
        // 3. Clear the IPC port 8000 (if lingering)
        mprintf("[XcosAI] Clearing port 8000...\n");
        host("powershell -Command " + dq + "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }" + dq);
    else
        host("pkill -f " + dq + server_script + dq);
    end
    
    mprintf('[XcosAI] Launching Python Backend...\n');
    // Start FastAPI in background
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
