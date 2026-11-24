// The part viewer for the printed-parts pages (three.js r128, same approach as pods-r1/viewer).
// part.json: {meshes:[{file, name, color, at:[x,y,z], lift, turn, axis:[x,y], main}], explode:bool}
// Model space is the STL's own (mm, Z up); the root turns it so Z is three's Y.
(function(){
  const el=document.getElementById('view'), status=document.getElementById('status');
  const reduce=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));
  renderer.localClippingEnabled=true;
  el.appendChild(renderer.domElement);
  const scene=new THREE.Scene();
  const cam=new THREE.PerspectiveCamera(32,1,0.5,8000);
  const controls=new THREE.OrbitControls(cam,renderer.domElement);
  controls.enableDamping=true; controls.autoRotate=!reduce; controls.autoRotateSpeed=1.2;
  scene.add(new THREE.HemisphereLight(0xffffff,0x8899aa,0.75));
  const sun=new THREE.DirectionalLight(0xffffff,0.75); sun.position.set(200,400,250); scene.add(sun);
  const fill=new THREE.DirectionalLight(0xffffff,0.3); fill.position.set(-300,100,-200); scene.add(fill);

  const root=new THREE.Group(); root.rotation.x=-Math.PI/2; scene.add(root);
  const model=new THREE.Group(); root.add(model);
  const clip=new THREE.Plane(new THREE.Vector3(-1,0,0),0);
  const mats=[], pieces=[];
  let cfg=null, box=null, radius=100;

  function resize(){const w=el.clientWidth,h=el.clientHeight;renderer.setSize(w,h,false);renderer.domElement.style.width='100%';renderer.domElement.style.height='100%';cam.aspect=w/h;cam.updateProjectionMatrix();}
  function home(){const d=radius*3.1; cam.position.set(d*0.62,d*0.55,d*0.75); controls.target.set(0,0,0); controls.update();}
  window.addEventListener('resize',()=>{resize();});
  resize();

  const $=id=>document.getElementById(id);
  const ex=$('explode'), exv=$('explode-v'), cut=$('cut'), cutAt=$('cut-at'), cutAx=$('cut-axis'), cutv=$('cut-v');

  function apply(){
    if(!cfg) return;
    const t=ex?+ex.value:0;
    pieces.forEach(p=>{
      const e=p.e, u=Math.min(1,t*2), lift=Math.max(0,(t-0.3)/0.7)*(e.lift||0);
      p.pivot.rotation.z=(e.turn||0)*Math.PI/180*u;   // + is anticlockwise seen from above: the bayonet's unlock
      p.pivot.position.z=e.at[2]+lift;
    });
    if(exv) exv.textContent=t<0.02?'together':t<0.5?'parting':'apart';
    const on=cut&&cut.checked;
    if(on){
      const ax=cutAx.value, k=ax==='x'?0:1, lo=box.min.getComponent(k), hi=box.max.getComponent(k);
      const c=lo+(hi-lo)*(+cutAt.value), ctr=(lo+hi)/2;
      // world = model - centre, turned: model x -> world x, model y -> world -z. Keep the far side, so the cut face looks at the camera.
      if(ax==='x'){clip.normal.set(-1,0,0); clip.constant=c-ctr;}
      else {clip.normal.set(0,0,-1); clip.constant=ctr-c;}
      cutv.textContent=ax+' '+c.toFixed(1);
    } else if(cutv) cutv.textContent='';
    mats.forEach(m=>{m.clippingPlanes=on?[clip]:[]; m.needsUpdate=true;});
  }

  function mat(color){
    const m=new THREE.MeshStandardMaterial({color:new THREE.Color(color),roughness:0.65,metalness:0,side:THREE.DoubleSide,clippingPlanes:[]});
    mats.push(m); return m;
  }

  fetch('part.json').then(r=>{if(!r.ok)throw new Error('part.json '+r.status);return r.json();}).then(c=>{
    cfg=c;
    const loader=new THREE.STLLoader();
    return Promise.all(c.meshes.map(e=>new Promise((ok,bad)=>loader.load(e.file,g=>ok([e,g]),undefined,()=>bad(new Error(e.file))))));
  }).then(list=>{
    box=new THREE.Box3();
    list.forEach(([e,g])=>{
      g.computeVertexNormals(); g.computeBoundingBox();
      const ax=e.axis||[0,0];
      const mesh=new THREE.Mesh(g,mat(e.color)); mesh.position.set(-ax[0],-ax[1],0);
      const pivot=new THREE.Group(); pivot.position.set(e.at[0]+ax[0],e.at[1]+ax[1],e.at[2]); pivot.add(mesh); model.add(pivot);
      const b=g.boundingBox.clone(); b.translate(new THREE.Vector3(e.at[0],e.at[1],e.at[2])); box.union(b);
      pieces.push({e,pivot,mesh});
      const t=document.querySelector('[data-show="'+e.name+'"]');
      if(t) t.addEventListener('change',()=>{pivot.visible=t.checked;});
      if(t) pivot.visible=t.checked;
    });
    const ctr=box.getCenter(new THREE.Vector3()); model.position.set(-ctr.x,-ctr.y,-ctr.z);
    radius=box.getSize(new THREE.Vector3()).length()/2;
    cam.near=radius/50; cam.far=radius*40; cam.updateProjectionMatrix();
    home(); status.hidden=true; apply();
  }).catch(err=>{status.textContent='The model did not load ('+err.message+'). Reload the page to try again.';});

  [ex,cut,cutAt,cutAx].forEach(i=>{if(i) i.addEventListener('input',apply);});
  if(cut) cut.addEventListener('change',apply);
  if(cutAx) cutAx.addEventListener('change',apply);
  const spin=$('spin');
  const spinText=()=>{spin.textContent=controls.autoRotate?'stop turning':'turn slowly';};
  spinText();
  spin.addEventListener('click',()=>{controls.autoRotate=!controls.autoRotate;spinText();});
  $('reset').addEventListener('click',home);
  renderer.domElement.addEventListener('pointerdown',()=>{if(controls.autoRotate){controls.autoRotate=false;spinText();}});
  (function loop(){requestAnimationFrame(loop);controls.update();renderer.render(scene,cam);})();
})();
