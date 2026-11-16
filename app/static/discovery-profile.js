(function () {
  'use strict';
  const ESSENTIAL = ['last_crop','last_harvest_result','main_difficulties','irrigation','mechanization','primary_goal','next_crop_preference','current_crop','planting_date','current_season_stage'];
  const OPTIONAL = ['fertilization','soil_management','cover_crops','other_crops','water_access','budget_constraints','technical_resources'];
  const envelope = () => ({value:null,status:'pending',source:'farmer_report',evidence:[],confidence:null,unknown_reason:null,updated_at:null,revision:0});
  function ensureFields(profile){for(const id of ESSENTIAL)if(!profile.fields[id])profile.fields[id]=envelope();return profile;}
  function create(property) {
    return {schema_version:'1.2.0',profile_id:crypto.randomUUID(),property_id:property.propertyId,person:{display_name:property.personName},property:{name:property.propertyName,area_hectares:property.areaHectares,geometry_source:'existing_property_registration'},fields:Object.fromEntries(ESSENTIAL.map(id=>[id,envelope()])),additional_fields:{},interview_history:[],revision:0,updated_at:new Date().toISOString()};
  }
  function apply(profile, response, transcript, history=[]) {
    if (response.base_profile_revision !== profile.revision) return {profile, applied:[]};
    const next=structuredClone(profile), applied=[];
    for (const patch of response.patches||[]) {
      const sourceTurn=patch.evidence_turn_id||response.turn_id;
      const evidenceText=sourceTurn===response.turn_id?transcript:history.find(x=>x.turn_id===sourceTurn&&x.speaker==='farmer')?.text;
      if (![...ESSENTIAL,...OPTIONAL].includes(patch.field) || !['set','merge'].includes(patch.operation) || !['confirmed','uncertain','unknown'].includes(patch.status) || !evidenceText?.includes(patch.evidence_excerpt)) continue;
      const target=ESSENTIAL.includes(patch.field)?next.fields:next.additional_fields;
      const old=target[patch.field]||envelope();
      const sameTurn=old.evidence.some(x=>x.turn_id===sourceTurn);
      const harvest=patch.field==='last_harvest_result'&&old.value;
      const unavailable=harvest?.qualitative_result&&patch.status==='unknown';
      if (sameTurn && !unavailable && (!patch.value || Object.entries(patch.value).every(([key,value])=>JSON.stringify(old.value?.[key])===JSON.stringify(value)))) continue;
      if (old.status==='confirmed' && patch.status==='uncertain' && patch.operation!=='set' && !sameTurn && patch.field!=='last_harvest_result') continue;
      const merge=old.value&&patch.value&&(sameTurn||harvest||patch.operation==='merge');
      const value=unavailable?{...old.value,estimate_unavailable:true}:merge?{...old.value,...patch.value}:patch.value;
      const excerpt=patch.evidence_excerpt.slice(0,180);
      const evidence=old.evidence.some(x=>x.turn_id===sourceTurn&&x.excerpt===excerpt)?old.evidence:[...old.evidence,{turn_id:sourceTurn,excerpt}].slice(-5);
      target[patch.field]={value,status:unavailable?'confirmed':patch.status,source:'farmer_report',evidence,confidence:patch.confidence,unknown_reason:unavailable?null:patch.unknown_reason||null,updated_at:new Date().toISOString(),revision:old.revision+1};
      applied.push({field:patch.field,before:old,after:target[patch.field]});
    }
    if(applied.length){next.revision++;next.updated_at=new Date().toISOString();}
    return {profile:next,applied};
  }
  function analysisInput(profile, property) {
    return {schema_version:'1.2.0',property_id:property.propertyId,geometry:property.geometry,area_hectares:property.areaHectares,agricultural_profile:activeFields(profile),data_quality:{pending_fields:ESSENTIAL.filter(x=>profile.fields[x].status==='pending'),uncertain_fields:ESSENTIAL.filter(x=>profile.fields[x].status==='uncertain'),unknown_fields:ESSENTIAL.filter(x=>profile.fields[x].status==='unknown')}};
  }
  function activeFields(profile){return Object.fromEntries(Object.entries({...profile.fields,...profile.additional_fields}).filter(([key])=>key!=='previous_crop'));}
  function ready(profile){return ESSENTIAL.every(id=>['confirmed','unknown'].includes(profile.fields[id]?.status));}
  function applyManual(profile, entries) {
    const next=structuredClone(profile),applied=[];
    for(const entry of entries){
      if(!ESSENTIAL.includes(entry.field)||!['confirmed','unknown'].includes(entry.status))continue;
      const old=next.fields[entry.field];
      const value=entry.status==='unknown'?null:entry.value;
      if(entry.status==='confirmed'&&(!value||typeof value!=='object'))continue;
      if(old.status===entry.status&&JSON.stringify(old.value)===JSON.stringify(value))continue;
      if(old.status==='uncertain'&&entry.status==='confirmed'&&JSON.stringify(old.value)===JSON.stringify(value))continue;
      const turnId=crypto.randomUUID();
      next.fields[entry.field]={value,status:entry.status,source:'user_edit',evidence:[...old.evidence,{turn_id:turnId,excerpt:'Preenchimento manual'}].slice(-5),confidence:'high',unknown_reason:entry.status==='unknown'?(entry.unknown_reason||'does_not_know'):null,updated_at:new Date().toISOString(),revision:old.revision+1};
      applied.push({field:entry.field,before:old,after:next.fields[entry.field],turn_id:turnId});
    }
    if(applied.length){next.revision++;next.updated_at=new Date().toISOString();}
    return {profile:next,applied};
  }
  window.AgrionProfile={ESSENTIAL,create,ensureFields,apply,applyManual,analysisInput,activeFields,ready};
})();
