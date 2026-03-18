function api_key = check_api_key(module_root_dir)
// check_api_key.sci
// Logic:
// 1. Check .env file in module root.
// 2. If present, extract GEMINI_API_KEY.
// 3. If absent or empty, show onboarding dialog.
// 4. Save to .env.

    env_path = module_root_dir + "/.env";
    api_key = "";

    if isfile(env_path) then
        fid = mopen(env_path, "r");
        lines = mgetl(fid, -1);
        mclose(fid);
        for i = 1:length(lines)
            idx = strindex(lines(i), "GEMINI_API_KEY=");
            if ~isempty(idx) then
                api_key = strtrim(part(lines(i), idx+15:length(lines(i))));
                break;
            end
        end
    end

    if api_key == "" then
        result = x_mdialog( ...
            ["No Gemini API key found."; ...
             "Generate one for free at:"; ...
             "https://aistudio.google.com/app/apikey"; ...
             ""; ...
             "Paste your key below:"], ...
            ["GEMINI_API_KEY"], ...
            [""]);
        if isempty(result) then
            api_key = "";
            return;
        end
        api_key = strtrim(result(1));
        if length(api_key) == 0 then
            return;
        end

        fid = mopen(env_path, "w");
        mputl("GEMINI_API_KEY=" + api_key, fid);
        mclose(fid);
    end
endfunction
