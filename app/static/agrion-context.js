(function(){
  'use strict';
  // O cadastro geográfico é a fonte atual de nomes, localização e geometria.
  function build(property, profile){
    if(!property?.propertyId)throw new Error('Propriedade não disponível.');
    if(profile&&profile.property_id!==property.propertyId)throw new Error('O perfil pertence a outra propriedade.');
    const fields={};
    for(const [id,entry] of Object.entries({...profile?.fields,...profile?.additional_fields})){
      fields[id]={value:entry.value??null,status:entry.status??'pending',source:entry.source??null,confidence:entry.confidence??null,unknown_reason:entry.unknown_reason??null,updated_at:entry.updated_at??null};
    }
    for(const id of window.AgrionProfile.ESSENTIAL){if(!fields[id])fields[id]={value:null,status:'pending',source:null,confidence:null,unknown_reason:null,updated_at:null};}
    return {schema_version:'1.0',person:{name:property.personName||null},property:{id:property.propertyId,name:property.propertyName||null,location_label:property.locationLabel||null,geometry:property.geometry||null,center_point:property.centerPoint||null,area_square_meters:property.areaSquareMeters??null,area_hectares:property.areaHectares??null,registered_at:property.registeredAt||null},agricultural_profile:{profile_id:profile?.profile_id||null,revision:profile?.revision??null,fields}};
  }
  async function load(){const property=window.AgrionPropertyStore.read();if(!property)throw new Error('Propriedade não disponível.');const profile=await window.AgrionRepository.getByPropertyId(property.propertyId);return build(property,profile);}
  window.AgrionContext={build,load};
})();
