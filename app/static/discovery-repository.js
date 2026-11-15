(function(){
  'use strict';
  const DB='agrion-discovery', VERSION=2;
  function open(){return new Promise((resolve,reject)=>{
    const r=indexedDB.open(DB,VERSION);
    let blocked=false;
    r.onupgradeneeded=event=>{
      const stores=[['agricultural_profiles','property_id'],['interviews','interview_id'],['interview_revisions','revision_id'],['pending_extractions','turn_id']];
      for(const [store,key] of stores){
        if(!r.result.objectStoreNames.contains(store))r.result.createObjectStore(store,{keyPath:key});
        else if(event.oldVersion<2)r.transaction.objectStore(store).clear();
      }
    };
    r.onsuccess=()=>{if(blocked)r.result.close();else resolve(r.result);};
    r.onerror=()=>reject(r.error);
    r.onblocked=()=>{blocked=true;reject(new Error('Discovery database upgrade blocked by another tab'));};
  });}
  async function get(store,key){const db=await open();return new Promise((resolve,reject)=>{const tx=db.transaction(store);const r=tx.objectStore(store).get(key);r.onsuccess=()=>resolve(r.result||null);r.onerror=()=>reject(r.error);tx.oncomplete=()=>db.close();});}
  async function put(store,value){const db=await open();return new Promise((resolve,reject)=>{const tx=db.transaction(store,'readwrite');tx.objectStore(store).put(value);tx.oncomplete=()=>{db.close();resolve(value);};tx.onerror=()=>{db.close();reject(tx.error);};});}
  async function all(store){const db=await open();return new Promise((resolve,reject)=>{const tx=db.transaction(store);const r=tx.objectStore(store).getAll();r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);tx.oncomplete=()=>db.close();});}
  async function remove(store,key){const db=await open();return new Promise((resolve,reject)=>{const tx=db.transaction(store,'readwrite');tx.objectStore(store).delete(key);tx.oncomplete=()=>{db.close();resolve();};tx.onerror=()=>{db.close();reject(tx.error);};});}
  async function savePatch(profile,revisions,interview){const db=await open();return new Promise((resolve,reject)=>{const tx=db.transaction(['agricultural_profiles','interview_revisions','interviews'],'readwrite');tx.objectStore('agricultural_profiles').put(profile);for(const revision of revisions)tx.objectStore('interview_revisions').put(revision);tx.objectStore('interviews').put(interview);tx.oncomplete=()=>{db.close();resolve();};tx.onerror=()=>{db.close();reject(tx.error);};});}
  window.AgrionRepository={get,put,all,remove,savePatch,getByPropertyId:id=>get('agricultural_profiles',id)};
})();
