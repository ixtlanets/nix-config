if length != 1 then
  error("expected exactly one input document")
elif (.[0] | type) != "object" then
  error("input document must be an object")
else
  .[0]
end
| if (.settings | type) == "null" then
  .settings = {}
elif (.settings | type) != "object" then
  error(".settings must be an object or null")
else
  .
end
| if (.settings.bindings | type) == "null" then
    .settings.bindings = {}
  elif (.settings.bindings | type) != "object" then
    error(".settings.bindings must be an object or null")
  else
    .
  end
| if (.settings.bindings.transcribe | type) != "null"
    and (.settings.bindings.transcribe | type) != "object"
  then
    error(".settings.bindings.transcribe must be an object or null")
  else
    .
  end
| if ($customWords[0] | type) != "array" then
    error("customWords must be an array")
  else
    .
  end
| .settings.bindings.transcribe = (
    if .settings.bindings.transcribe == null then
      {
        "id": "transcribe",
        "name": "Transcribe",
        "description": "Converts your speech into text.",
        "default_binding": "ctrl+space",
        "current_binding": "alt_right"
      }
    else
      .settings.bindings.transcribe + { "current_binding": "alt_right" }
    end
  )
| .settings.keyboard_implementation = "handy_keys"
| .settings.push_to_talk = true
| .settings.paste_method = "ctrl_shift_v"
| .settings.autostart_enabled = false
| .settings.update_checks_enabled = false
| .settings.custom_words = $customWords[0]
