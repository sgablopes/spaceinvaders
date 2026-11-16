(function(){
  'use strict';
  const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const field=(id,label,control,hint='')=>`<div class="discovery-field"><label for="manual-${id}">${label}</label>${hint?`<small>${hint}</small>`:''}${control}</div>`;
  const input=(id,value='',placeholder='')=>`<input id="manual-${id}" name="${id}" type="text" maxlength="180" value="${escapeHtml(value)}" placeholder="${escapeHtml(placeholder)}">`;
  const select=(id,options,value='')=>`<select id="manual-${id}" name="${id}"><option value="">Selecione</option>${options.map(([key,label])=>`<option value="${key}" ${value===key?'selected':''}>${label}</option>`).join('')}</select>`;
  const unknown=(id,checked=false)=>`<label class="discovery-inline"><input type="checkbox" name="${id}_unknown" ${checked?'checked':''}> Não sei informar</label>`;
  function markup(profile){
    const fields=profile.fields,value=id=>fields[id]?.value||{},isUnknown=id=>fields[id]?.status==='unknown';
    const never=value('last_crop').never_cultivated===true||value('last_crop').no_previous_cultivation===true;
    return `<form id="discoveryManualForm" class="discovery-manual-form" novalidate>
      <p>Preencha o que souber. Campos vazios não impedem a análise preliminar.</p>
      ${field('current_crop','O que está plantado na safra atual?',input('current_crop',value('current_crop').crop,'Ex.: milho')+`<label class="discovery-inline"><input type="checkbox" name="not_planted" ${value('current_crop').not_planted===true?'checked':''}> Não há cultivo atual</label>`+unknown('current_crop',isUnknown('current_crop')))}
      <label class="discovery-inline discovery-never"><input type="checkbox" name="no_previous_cultivation" ${never?'checked':''}> Não houve cultivo anterior</label>
      ${field('last_crop','Cultura anterior',input('last_crop',value('last_crop').crop,'Ex.: milho')+unknown('last_crop',isUnknown('last_crop')))}
      ${field('harvest_result','Resultado da colheita anterior',select('harvest_result',[['good','Boa'],['average','Média'],['poor','Ruim'],['no_harvest','Não houve colheita']],value('last_harvest_result').qualitative_result)+`<details class="discovery-harvest-details"><summary>Adicionar detalhes da colheita (opcional)</summary><div class="discovery-field-row"><div><label for="manual-harvest_quantity">Quantidade aproximada</label><input id="manual-harvest_quantity" name="harvest_quantity" type="number" min="0" step="any" value="${escapeHtml(value('last_harvest_result').quantity??'')}"></div><div><label for="manual-harvest_unit">Unidade</label>${select('harvest_unit',[['sacas','Sacas'],['toneladas','Toneladas'],['kg','Quilos'],['unidades','Unidades']],value('last_harvest_result').unit)}</div></div><div class="discovery-field-row"><div><label for="manual-harvest_amount">Valor aproximado (R$)</label><input id="manual-harvest_amount" name="harvest_amount" type="number" min="0" step="any" value="${escapeHtml(value('last_harvest_result').financial_amount??'')}"></div><div><label for="manual-harvest_kind">Tipo de valor</label>${select('harvest_kind',[['revenue','Receita'],['profit','Lucro'],['unknown','Não sei']],value('last_harvest_result').financial_kind)}</div></div><label class="discovery-inline"><input type="checkbox" name="estimate_unavailable" ${value('last_harvest_result').estimate_unavailable===true?'checked':''}> Continuar sem quantidade e valor</label></details>${unknown('last_harvest_result',isUnknown('last_harvest_result'))}`,'Basta informar como foi a colheita. Quantidade e valor são opcionais.')}
      ${field('main_difficulties','Principais dificuldades',input('main_difficulties',(value('main_difficulties').free_text||[]).join('; '),'Ex.: falta de chuva, pragas')+`<label class="discovery-inline"><input type="checkbox" name="no_difficulties" ${value('main_difficulties').explicit_none===true?'checked':''}> Não tive dificuldades</label>`+unknown('main_difficulties',isUnknown('main_difficulties')))}
      ${field('irrigation','Irrigação',select('irrigation',[['rainfed','Dependo da chuva'],['irrigated','Uso irrigação'],['mixed','Chuva e irrigação']],value('irrigation').water_regime)+unknown('irrigation',isUnknown('irrigation')))}
      ${field('mechanization','Máquinas e trabalho',select('mechanization',[['manual','Principalmente manual'],['mixed','Manual e máquinas'],['mechanized','Principalmente máquinas'],['automated','Automatizado']],value('mechanization').work_mode)+input('equipment',(value('mechanization').equipment||[]).join(', '),'Equipamentos usados, se houver')+unknown('mechanization',isUnknown('mechanization')))}
      ${field('primary_goal','Objetivo da próxima safra',select('primary_goal',[['maximize_profit','Aumentar lucro'],['increase_yield','Aumentar produção'],['restore_soil','Recuperar solo'],['reduce_risk','Reduzir riscos'],['reduce_costs','Reduzir custos'],['diversify','Diversificar'],['other','Outro']],value('primary_goal').category)+input('goal_description',value('primary_goal').description,'Conte mais, se quiser')+unknown('primary_goal',isUnknown('primary_goal')))}
      ${field('next_crop_preference','Preferência de plantio',input('next_crop_preference',value('next_crop_preference').crop,'Cultura preferida')+`<label class="discovery-inline"><input type="checkbox" name="no_preference" ${value('next_crop_preference').no_preference===true?'checked':''}> Não tenho preferência</label>`+unknown('next_crop_preference',isUnknown('next_crop_preference')))}
      ${field('planting_date','Quando plantou a safra atual?',input('planting_date',value('planting_date').date,'AAAA-MM-DD, AAAA-MM ou AAAA')+unknown('planting_date',isUnknown('planting_date')),'Informe a data ou o mês e ano, se souber.')}
      ${field('current_season_stage','Fase da safra atual',select('current_season_stage',[['not_started','Ainda não comecei'],['planning','Planejamento'],['soil_preparation','Preparo do solo'],['planting','Plantio'],['growing','Crescimento'],['flowering','Floração'],['fruiting','Frutificação'],['harvesting','Colheita'],['post_harvest','Após colheita'],['fallow','Pousio'],['other','Outra']],value('current_season_stage').stage)+unknown('current_season_stage',isUnknown('current_season_stage')))}
      <p id="discoveryManualError" class="discovery-form-error" role="alert" hidden></p>
      <button class="btn btn-primary" type="submit" name="action" value="continue">Salvar e continuar para análise</button><button class="btn btn-secondary" type="submit" name="action" value="save">Salvar para continuar depois</button>
    </form>`;
  }
  function collect(form){
    const data=new FormData(form),get=id=>String(data.get(id)||'').trim(),yes=id=>data.has(id),entries=[];
    const add=(field,value)=>{if(yes(`${field}_unknown`)&&!(field==='current_crop'&&yes('not_planted'))&&!(field==='planting_date'&&yes('not_planted')))entries.push({field,status:'unknown',value:null});else if(value)entries.push({field,status:'confirmed',value});};
    if(yes('no_previous_cultivation')){
      entries.push({field:'last_crop',status:'confirmed',value:{crop:null,no_previous_cultivation:true}},{field:'last_harvest_result',status:'confirmed',value:{qualitative_result:'not_applicable'}});
    }else{
      add('last_crop',get('last_crop')?{crop:get('last_crop')}:null);
      const skip=yes('estimate_unavailable')||yes('last_harvest_result_unknown');
      const quantity=skip?'':get('harvest_quantity'),unit=get('harvest_unit'),amount=skip?'':get('harvest_amount'),kind=get('harvest_kind');
      if([quantity,amount].some(v=>v!==''&&(!Number.isFinite(Number(v))||Number(v)<0)))throw Error('Informe números válidos ou marque Continuar sem quantidade e valor.');
      if(quantity&&!unit)throw Error('Escolha a unidade da quantidade colhida.');
      if(amount&&!kind)throw Error('Indique se o valor é receita, lucro ou se não sabe.');
      const result=get('harvest_result');
      const harvest={};if(result)harvest.qualitative_result=result;
      if(quantity){harvest.quantity=Number(quantity);harvest.unit=unit;}
      if(amount){harvest.financial_amount=Number(amount);harvest.currency='BRL';harvest.financial_kind=kind;}
      if(yes('estimate_unavailable'))harvest.estimate_unavailable=true;
      add('last_harvest_result',Object.keys(harvest).length?harvest:null);
    }
    const difficulties=get('main_difficulties');add('main_difficulties',yes('no_difficulties')?{categories:[],free_text:[],explicit_none:true}:difficulties?{categories:[],free_text:difficulties.split(';').map(x=>x.trim()).filter(Boolean),explicit_none:false}:null);
    add('irrigation',get('irrigation')?{water_regime:get('irrigation')}:null);
    add('mechanization',get('mechanization')?{work_mode:get('mechanization'),equipment:get('equipment').split(',').map(x=>x.trim()).filter(Boolean)}:null);
    add('primary_goal',get('primary_goal')?{category:get('primary_goal'),description:get('goal_description')||null}:null);
    add('next_crop_preference',yes('no_preference')?{crop:null,no_preference:true}:get('next_crop_preference')?{crop:get('next_crop_preference'),no_preference:false}:null);
    add('current_crop',yes('not_planted')?{crop:null,not_planted:true}:get('current_crop')?{crop:get('current_crop')}:null);
    const date=get('planting_date');
    if(date&&!yes('planting_date_unknown')&&!yes('not_planted')){
      if(!/^(\d{4})(?:-(0[1-9]|1[0-2])(?:-(0[1-9]|[12]\d|3[01]))?)?$/.test(date))throw Error('Informe a data de plantio como AAAA-MM-DD, AAAA-MM ou AAAA.');
      if(date.startsWith('0000')||(date.length===10&&new Date(date+'T00:00:00Z').toISOString().slice(0,10)!==date))throw Error('Informe uma data de plantio válida.');
    }
    add('planting_date',yes('not_planted')?{not_planted:true}:date?{date}:null);
    add('current_season_stage',get('current_season_stage')?{stage:get('current_season_stage')}:null);
    return entries;
  }
  window.AgrionManual={markup,collect};
})();
