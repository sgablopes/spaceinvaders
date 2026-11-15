(function(){
  'use strict';
  const DB='agrion-dashboard',VERSION=1,STORE='snapshots';
  function open(){return new Promise((resolve,reject)=>{const request=indexedDB.open(DB,VERSION);request.onupgradeneeded=()=>{if(!request.result.objectStoreNames.contains(STORE))request.result.createObjectStore(STORE,{keyPath:'key'});};request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);request.onblocked=()=>reject(new Error('Armazenamento indisponível'));});}
  async function get(key){try{const db=await open();return await new Promise((resolve,reject)=>{const tx=db.transaction(STORE,'readonly');const request=tx.objectStore(STORE).get(key);request.onsuccess=()=>resolve(request.result||null);request.onerror=()=>reject(request.error);tx.oncomplete=()=>db.close();tx.onerror=()=>db.close();});}catch(_){return null;}}
  async function put(record){try{const db=await open();return await new Promise((resolve,reject)=>{const tx=db.transaction(STORE,'readwrite');tx.objectStore(STORE).put(record);tx.oncomplete=()=>{db.close();resolve(true);};tx.onerror=()=>{db.close();reject(tx.error);};});}catch(_){return false;}}
  window.AgrionDashboardCache={get,put};
})();
