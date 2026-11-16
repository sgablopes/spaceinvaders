from pathlib import Path
p=Path('app/static/discovery-manual.js');s=p.read_text(encoding='utf-8')
s=s.replace("const never=value('last_crop').never_cultivated===true;", "const never=value('last_crop').never_cultivated===true||value('last_crop').no_previous_cultivation===true;")
s=s.replace('Preencha o que souber. Você pode salvar respostas parciais e voltar depois.', 'Preencha o que souber. Campos vazios não impedem a análise preliminar.')
lines=s.splitlines();current=next(l for l in lines if "${field('current_crop'" in l)
lines=[l for l in lines if "${field('previous_crop'" not in l and "${field('current_crop'" not in l]
idx=next(i for i,l in enumerate(lines) if '<label class="discovery-inline discovery-never"' in l)
current=current.replace("+unknown('current_crop'", "+`<label class=\"discovery-inline\"><input type=\"checkbox\" name=\"not_planted\" ${value('current_crop').not_planted===true?'checked':''}> Não há cultivo atual</label>`+unknown('current_crop'")
lines.insert(idx,current);s='\n'.join(lines)+'\n'
s=s.replace('name="never_cultivated"','name="no_previous_cultivation"').replace('Nunca plantei nesta área','Não houve cultivo anterior').replace("field('last_crop','Última cultura'", "field('last_crop','Cultura anterior'")
s=s.replace('Resultado da última colheita','Resultado da colheita anterior')
s=s.replace('+`<div class="discovery-field-row"><div><label for="manual-harvest_quantity">', '+`<details class="discovery-harvest-details"><summary>Adicionar detalhes da colheita (opcional)</summary><div class="discovery-field-row"><div><label for="manual-harvest_quantity">')
s=s.replace("${unknown('last_harvest_result',isUnknown('last_harvest_result'))}`", "</details>${unknown('last_harvest_result',isUnknown('last_harvest_result'))}`")
s=s.replace('Não consigo estimar quantidade nem valor','Continuar sem quantidade e valor')
s=s.replace('Se souber, informe quantidade ou valor. Não é preciso preencher os dois.', 'Basta informar como foi a colheita. Quantidade e valor são opcionais.')
s=s.replace('<button class="btn btn-primary" type="submit">Salvar respostas</button>', '<button class="btn btn-primary" type="submit" name="action" value="continue">Salvar e continuar para análise</button><button class="btn btn-secondary" type="submit" name="action" value="save">Salvar para continuar depois</button>')
s=s.replace("yes('never_cultivated')", "yes('no_previous_cultivation')")
s=s.replace("{field:'last_crop',status:'confirmed',value:{crop:null,never_cultivated:true}},{field:'previous_crop',status:'confirmed',value:{crop:null,no_previous_cultivation:true}},", "{field:'last_crop',status:'confirmed',value:{crop:null,no_previous_cultivation:true}},")
s='\n'.join(l for l in s.splitlines() if "add('previous_crop'" not in l)+'\n'
s=s.replace("      const quantity=get('harvest_quantity'),unit=get('harvest_unit'),amount=get('harvest_amount'),kind=get('harvest_kind');", "      const skip=yes('estimate_unavailable')||yes('last_harvest_result_unknown');\n      const quantity=skip?'':get('harvest_quantity'),unit=get('harvest_unit'),amount=skip?'':get('harvest_amount'),kind=get('harvest_kind');\n      if([quantity,amount].some(v=>v!==''&&(!Number.isFinite(Number(v))||Number(v)<0)))throw Error('Informe números válidos ou marque Continuar sem quantidade e valor.');")
s=s.replace("add('current_crop',get('current_crop')?{crop:get('current_crop')}:null);", "add('current_crop',yes('not_planted')?{crop:null,not_planted:true}:get('current_crop')?{crop:get('current_crop')}:null);")
s=s.replace("&&!yes('no_previous_cultivation')", "&&!yes('not_planted')")
s=s.replace("add('planting_date',yes('no_previous_cultivation')", "add('planting_date',yes('not_planted')")
a=s.index("    if(yes('no_previous_cultivation')){",s.index("    add('current_season_stage'"));b=s.index('    return entries;',a);s=s[:a]+s[b:]
# Explicit no-current selection takes precedence over an old unknown checkbox.
s=s.replace("if(yes(`${field}_unknown`))", "if(yes(`${field}_unknown`)&&!(field==='current_crop'&&yes('not_planted'))&&!(field==='planting_date'&&yes('not_planted')))")
p.write_text(s,encoding='utf-8')
