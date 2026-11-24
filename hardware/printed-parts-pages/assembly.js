// The scene viewer for the printed-parts pages that show several parts in place (three.js r128).
// scene.json: {meshes:[{file|cylinder, key, label, color, opacity, m:[12 row-major 3x4], explode:[x,y,z],
//               instances:[[dx,dy,dz]...], instance_explode:[[x,y,z]...], hidden, note, group, bought}], explode_max}
// group: the key puts the entry under that heading, with show/hide buttons for the group; bought: a striped swatch.
// Model space is mm with Z up. Each mesh goes through its own m, then moves by explode * the slider.
(function(){
  const el=document.getElementById('view'), status=document.getElementById('status');
  const reduce=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));
  renderer.localClippingEnabled=true;
  el.appendChild(renderer.domElement);
  const scene=new THREE.Scene();
  const cam=new THREE.PerspectiveCamera(32,1,0.5,20000);
  cam.up.set(0,0,1);
  const controls=new THREE.OrbitControls(cam,renderer.domElement);
  controls.enableDamping=true; controls.autoRotate=!reduce; controls.autoRotateSpeed=1.0;
  scene.add(new THREE.HemisphereLight(0xffffff,0x8899aa,0.75));
  const sun=new THREE.DirectionalLight(0xffffff,0.75); sun.position.set(300,-500,700); scene.add(sun);
  const fill=new THREE.DirectionalLight(0xffffff,0.3); fill.position.set(-400,300,-100); scene.add(fill);
  const model=new THREE.Group(); scene.add(model);
  const clip=new THREE.Plane(new THREE.Vector3(-1,0,0),0);
  const mats=[], pieces=[];
  let cfg=null, box=null, ctr=new THREE.Vector3(), radius=100;

  function resize(){const w=el.clientWidth,h=el.clientHeight;renderer.setSize(w,h,false);renderer.domElement.style.width='100%';renderer.domElement.style.height='100%';cam.aspect=w/h;cam.updateProjectionMatrix();}
  function home(){   // back off until the bounding sphere fits the narrower of the two fields of view
    const v=cam.fov*Math.PI/180, h=2*Math.atan(Math.tan(v/2)*cam.aspect), d=radius/Math.sin(Math.min(v,h)/2)*1.02;
    const dir=new THREE.Vector3(0.55,-0.8,0.3).normalize();
    cam.position.copy(dir.multiplyScalar(d)); controls.target.set(0,0,0); controls.update();}
  window.addEventListener('resize',resize);
  resize();

  const $=id=>document.getElementById(id);
  const ex=$('explode'), exv=$('explode-v'), cut=$('cut'), cutAt=$('cut-at'), cutAx=$('cut-axis'), cutFlip=$('cut-flip'), cutv=$('cut-v');
  const legend=$('legend');

  function apply(){
    if(!cfg) return;
    const t=ex?+ex.value:0;
    pieces.forEach(p=>{p.obj.position.set(p.base[0]+p.ex[0]*t,p.base[1]+p.ex[1]*t,p.base[2]+p.ex[2]*t);});
    if(exv) exv.textContent=t<0.02?'together':t<0.5?'parting':'apart';
    const on=cut&&cut.checked;
    if(on){
      const ax=cutAx.value, k={x:0,y:1,z:2}[ax], lo=box.min.getComponent(k), hi=box.max.getComponent(k);
      const c=lo+(hi-lo)*(+cutAt.value), flip=cutFlip&&cutFlip.checked?-1:1;
      const n=new THREE.Vector3(); n.setComponent(k,-flip);
      clip.normal.copy(n); clip.constant=flip*(c-ctr.getComponent(k));   // keeps the side below c (or above, flipped)
      cutv.textContent=ax+' '+c.toFixed(0)+' mm';
    } else if(cutv) cutv.textContent='';
    mats.forEach(m=>{m.clippingPlanes=on?[clip]:[]; m.needsUpdate=true;});
  }

  function mat(e){
    const op=e.opacity==null?1:e.opacity;
    const m=new THREE.MeshStandardMaterial({color:new THREE.Color(e.color),roughness:0.6,metalness:e.metal?0.4:0,
      side:THREE.DoubleSide,transparent:op<1,opacity:op,depthWrite:op>=1,clippingPlanes:[]});
    mats.push(m); return m;
  }

  function matrix(e){
    const M=new THREE.Matrix4();
    if(e.m){const a=e.m; M.set(a[0],a[1],a[2],a[3],a[4],a[5],a[6],a[7],a[8],a[9],a[10],a[11],0,0,0,1);}
    return M;
  }

  const groups={};
  function groupBox(name){   // one row per group in the key, with its own show/hide buttons
    if(!name) return legend;
    if(groups[name]) return groups[name].box;
    const g=document.createElement('div'); g.className='lgroup';
    const h=document.createElement('span'); h.className='lgroup-h'; h.textContent=name;
    const on=document.createElement('button'); on.type='button'; on.textContent='show';
    const off=document.createElement('button'); off.type='button'; off.textContent='hide';
    const box=document.createElement('div'); box.className='lgroup-keys';
    g.append(h,on,off,box); legend.appendChild(g);
    const cbs=[]; groups[name]={box,cbs};
    const flip=v=>cbs.forEach(cb=>{if(cb.checked!==v){cb.checked=v;cb.dispatchEvent(new Event('change'));}});
    on.addEventListener('click',()=>flip(true)); off.addEventListener('click',()=>flip(false));
    on.setAttribute('aria-label','show every part in: '+name); off.setAttribute('aria-label','hide every part in: '+name);
    return box;
  }

  function addLegend(e,objs){
    if(!legend) return;
    const id='show-'+e.key;
    const lab=document.createElement('label'); lab.className='key';
    const cb=document.createElement('input'); cb.type='checkbox'; cb.id=id; cb.checked=!e.hidden;
    const sw=document.createElement('span'); sw.className='sw'; sw.style.background=e.color; if(e.opacity!=null&&e.opacity<1) sw.style.opacity=0.55;
    const tx=document.createElement('span'); tx.textContent=e.label+(e.note?' ('+e.note+')':'');
    if(e.bought) sw.classList.add('bought');
    lab.append(cb,sw,tx); groupBox(e.group).appendChild(lab);
    if(e.group) groups[e.group].cbs.push(cb);
    const set=()=>objs.forEach(o=>{o.visible=cb.checked;});
    cb.addEventListener('change',set); set();
    return cb;
  }

  fetch('scene.json').then(r=>{if(!r.ok)throw new Error('scene.json '+r.status);return r.json();}).then(c=>{
    cfg=c;
    const loader=new THREE.STLLoader();
    return Promise.all(c.meshes.map(e=>e.cylinder?Promise.resolve([e,null]):new Promise((ok,bad)=>loader.load(e.file,g=>ok([e,g]),undefined,()=>bad(new Error(e.file))))));
  }).then(list=>{
    box=new THREE.Box3();
    const cbs=[];
    list.forEach(([e,g])=>{
      if(e.cylinder){
        const cy=e.cylinder; g=new THREE.CylinderGeometry(cy.r,cy.r,cy.z1-cy.z0,48,1,false);
        g.rotateX(Math.PI/2); g.translate(cy.x||0,cy.y||0,(cy.z0+cy.z1)/2);
      }
      g.computeVertexNormals();
      const M=matrix(e), m=mat(e), objs=[];
      const inst=e.instances||[[0,0,0]], iex=e.instance_explode||inst.map(()=>[0,0,0]);
      inst.forEach((d,i)=>{
        const mesh=new THREE.Mesh(g,m); mesh.applyMatrix4(M);
        const obj=new THREE.Group(); obj.add(mesh); model.add(obj);
        // an instance's offset is in the mesh's own frame: carry it through m's rotation
        const off=new THREE.Vector3(d[0],d[1],d[2]).applyMatrix3(new THREE.Matrix3().setFromMatrix4(M));
        const ie=new THREE.Vector3(iex[i][0],iex[i][1],iex[i][2]).applyMatrix3(new THREE.Matrix3().setFromMatrix4(M));
        const base=[off.x,off.y,off.z], exv=e.explode||[0,0,0];
        pieces.push({obj,base,ex:[exv[0]+ie.x,exv[1]+ie.y,exv[2]+ie.z]});
        obj.position.set(base[0],base[1],base[2]); obj.updateMatrixWorld(true);
        box.union(new THREE.Box3().setFromObject(obj));
        objs.push(obj);
      });
      cbs.push(addLegend(e,objs));
    });
    ctr=box.getCenter(new THREE.Vector3()); model.position.set(-ctr.x,-ctr.y,-ctr.z);
    radius=box.getSize(new THREE.Vector3()).length()/2;
    cam.near=radius/80; cam.far=radius*40; cam.updateProjectionMatrix();
    const all=$('all'), none=$('none');
    if(all) all.addEventListener('click',()=>cbs.forEach(cb=>{if(cb&&!cb.checked){cb.checked=true;cb.dispatchEvent(new Event('change'));}}));
    if(none) none.addEventListener('click',()=>cbs.forEach(cb=>{if(cb&&cb.checked){cb.checked=false;cb.dispatchEvent(new Event('change'));}}));
    home(); status.hidden=true; apply();
  }).catch(err=>{status.textContent='The model did not load ('+err.message+'). Reload the page to try again.';});

  [ex,cutAt].forEach(i=>{if(i) i.addEventListener('input',apply);});
  [cut,cutAx,cutFlip].forEach(i=>{if(i) i.addEventListener('change',apply);});
  const spin=$('spin');
  const spinText=()=>{spin.textContent=controls.autoRotate?'stop turning':'turn slowly';};
  spinText();
  spin.addEventListener('click',()=>{controls.autoRotate=!controls.autoRotate;spinText();});
  $('reset').addEventListener('click',home);
  renderer.domElement.addEventListener('pointerdown',()=>{if(controls.autoRotate){controls.autoRotate=false;spinText();}});
  (function loop(){requestAnimationFrame(loop);controls.update();renderer.render(scene,cam);})();
})();
