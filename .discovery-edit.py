from pathlib import Path
p=Path('app/api/discovery.py');s=p.read_text(encoding='utf-8')
s=s.replace('"last_crop", "previous_crop",','"last_crop",')
s=s.replace('LANGUAGES = {"pt-BR", "en-US", "es-US"}', 'LANGUAGES = {"pt-BR", "en-US"}')
s=s.replace('    harvest_estimate_pending = state.get("harvest_estimate_pending") is True\n','')
a=s.index('    elif harvest_estimate_pending:');b=s.index('    elif uncertain',a);s=s[:a]+s[b:]
s=s.replace('last_crop is the most recent crop; previous_crop is immediately before it;', 'current_crop is the crop currently planted; last_crop is the immediately preceding crop (or the most recent completed crop if none is planted now);')
s=s.replace('last_crop and previous_crop use crop as a string; if the area was never cultivated, last_crop uses never_cultivated=true and previous_crop uses no_previous_cultivation=true, both with crop=null.', 'last_crop uses crop as a string, or crop=null with no_previous_cultivation=true if no preceding crop. current_crop uses crop as a string, or crop=null and not_planted=true if nothing is planted now. never_cultivated=true is also accepted for last_crop when explicitly stated. Do not ask about a third crop.')
s=s.replace('    never_cultivated: bool | None = None', '    never_cultivated: bool | None = None\n    not_planted: bool | None = None')
s=s.replace('"previous_crop": CropValue, ', '')
s=s.replace('        return set(value) == {"crop"} and isinstance(value["crop"], str) and bool(value["crop"].strip())', '        return (set(value) == {"crop"} and isinstance(value["crop"], str) and bool(value["crop"].strip())\n            or set(value) <= {"crop", "not_planted"} and value.get("crop") is None and value.get("not_planted") is True)')
s=s.replace('    if patch.field in {"last_crop", "previous_crop"}:','    if patch.field == "last_crop":')
s=s.replace('return crop is None and (patch.field == "last_crop" and value.get("never_cultivated") is True\n            or patch.field == "previous_crop" and value.get("no_previous_cultivation") is True)', 'return crop is None and (value.get("never_cultivated") is True or value.get("no_previous_cultivation") is True)')
s=s.replace('last_crop.never_cultivated=true, previous_crop.no_previous_cultivation=true e', 'last_crop.never_cultivated=true e')
s=s.replace('current_crop unknown com motivo does_not_know', 'current_crop={crop:null,not_planted:true} confirmado')
s=s.replace('Registre current_crop apenas para a cultura que está plantada atualmente.', 'Registre current_crop apenas para a cultura que está plantada atualmente. last_crop é somente a cultura imediatamente anterior, ou a última encerrada se não houver cultivo atual. Não registre nem solicite uma terceira safra. Quantidade e valor de colheita são opcionais; um resultado qualitativo já é suficiente.')
a=s.index('        harvest = next(');b=s.index('        if targets:',a);s=s[:a]+s[b:]
s=s.replace('and patch.value.get("never_cultivated") is True), None)', 'and (patch.value.get("never_cultivated") is True or patch.value.get("no_previous_cultivation") is True)), None)')
s=s.replace('{"previous_crop", "last_harvest_result"}', '{"last_harvest_result"}')
s=s.replace('for field, value in (("previous_crop", {"crop": None, "no_previous_cultivation": True}),\n                                 ("last_harvest_result", {"qualitative_result": "not_applicable"})):', 'for field, value in (("last_harvest_result", {"qualitative_result": "not_applicable"}),):')
s=s.replace('Conheça última cultura, cultura imediatamente anterior, resultado da colheita,', 'Conheça a cultura atual e apenas a imediatamente anterior, resultado da colheita anterior,')
s=s.replace('Use o estado do aplicativo para escolher lacunas;', 'Quantidade e valor financeiro são opcionais. Aceite um resultado qualitativo da colheita como resposta suficiente; não exija estimativas numéricas. Aceite desconhecimento ou recusa e avance. Use o estado do aplicativo para escolher lacunas;')
s=s.replace('            voice = "Orus"', '            voice = "Orus" if language == "pt-BR" else None')
s=s.replace('                speech_config = {"languageCode": language}\n                if voice:\n                    speech_config["voiceConfig"] = {"prebuiltVoiceConfig": {"voiceName": voice}}', '                speech_config = _speech_config(language)')
pos=s.index('\ndef _live_state_instruction')
s=s[:pos]+'''\ndef _speech_config(language):
    if language not in LANGUAGES:
        raise ValueError('unsupported_language')
    config = {"languageCode": language}
    if language == 'pt-BR':
        config['voiceConfig'] = {'prebuiltVoiceConfig': {'voiceName': 'Orus'}}
    return config

'''+s[pos:]
p.write_text(s,encoding='utf-8')
p=Path('app/static/discovery-profile.js');s=p.read_text(encoding='utf-8').replace("'last_crop','previous_crop',", "'last_crop',")
s=s.replace("schema_version:'1.1.0'", "schema_version:'1.2.0'")
s=s.replace('agricultural_profile:{...profile.fields,...profile.additional_fields}', 'agricultural_profile:activeFields(profile)')
s=s.replace('  function applyManual(profile, entries) {', '''  function activeFields(profile){return Object.fromEntries(Object.entries({...profile.fields,...profile.additional_fields}).filter(([key])=>key!=='previous_crop'));}
  function ready(profile){return ESSENTIAL.every(id=>['confirmed','unknown'].includes(profile.fields[id]?.status));}
  function applyManual(profile, entries) {''')
s=s.replace("unknown_reason:entry.status==='unknown'?'does_not_know':null", "unknown_reason:entry.status==='unknown'?(entry.unknown_reason||'does_not_know'):null")
s=s.replace('applyManual,analysisInput};','applyManual,analysisInput,activeFields,ready};')
p.write_text(s,encoding='utf-8')
p=Path('app/static/agrion-context.js');s=p.read_text(encoding='utf-8').replace('      fields[id]=','      if(id===\'previous_crop\')continue;\n      fields[id]=');p.write_text(s,encoding='utf-8')
p=Path('app/static/agrion-dashboard.js');s=p.read_text(encoding='utf-8').replace("[['last_crop','Última cultura'],['previous_crop','Cultura anterior']]", "[['last_crop','Cultura anterior']]").replace("if(id==='current_crop')return v.crop||'Não informado';", "if(id==='current_crop')return v.not_planted?'Sem cultivo atual':v.crop||'Não informado';");p.write_text(s,encoding='utf-8')
