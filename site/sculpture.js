// Original GPU point sculpture. Its shapes are artwork, not model data.
(function () {
  'use strict';
  const canvas = document.querySelector('#sculpture-canvas');
  if (!canvas) return;
  const stage = document.querySelector('.cover-stage');
  const fallback = document.querySelector('.sculpture-fallback');
  const pause = document.querySelector('#sculpture-pause');
  const controls = document.querySelector('.sculpture-controls');
  const hint = document.querySelector('.sculpture-hint');
  const modeButtons = [...document.querySelectorAll('[data-sculpture-mode]')];
  const burstButton = document.querySelector('#sculpture-burst');
  const resetButton = document.querySelector('#sculpture-reset');
  const status = document.querySelector('#sculpture-status');
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const gl = canvas.getContext('webgl', {alpha:true, antialias:false, premultipliedAlpha:true});
  if (!gl) return; // The matching static drawing and reading paths remain available.
  const vertex = `
  attribute vec3 aKnot,aFork,aOrbit,aNormal;
  attribute vec2 aSeed;
  uniform vec3 uMorph;
  uniform vec2 uRes,uPointer;
  uniform vec2 uTrail[3];
  uniform float uTrailW[3];
  uniform float uTime,uYaw,uPitch,uBurst,uDpr,uDark,uActive;
  varying vec3 vColor;
  varying float vAlpha;
  mat3 turn(float a,float b){
    float c=cos(a),s=sin(a),q=cos(b),r=sin(b);
    return mat3(c,s*r,-s*q,0.,q,r,s,-c*r,c*q);
  }
  vec3 wake(vec3 p,vec2 c,float w){
    vec2 d=p.xy-c;
    float infl=exp(-dot(d,d)*1.6)*w;
    p.xy+=d*infl*.28;
    p.z+=infl*.22;
    return p;
  }
  void main(){
    mat3 rotation=turn(uYaw,uPitch);
    vec3 p=aKnot*uMorph.x+aFork*uMorph.y+aOrbit*uMorph.z;
    vec3 n=normalize(aNormal);
    float wave=sin(aSeed.x*5.-uTime*1.4+aSeed.y*2.);
    p+=n*wave*.045;
    p=rotation*p; n=rotation*n;
    float radius=length(p.xy-uPointer);
    float influence=exp(-radius*radius*1.5)*uActive;
    p.xy+=(p.xy-uPointer)*influence*.8;
    p.z+=influence*.8;
    p=wake(p,uTrail[0],uTrailW[0]);
    p=wake(p,uTrail[1],uTrailW[1]);
    p=wake(p,uTrail[2],uTrailW[2]);
    vec3 scatter=normalize(p+vec3(sin(aSeed.x*13.),cos(aSeed.y*7.),sin(aSeed.y*11.)));
    p+=scatter*uBurst*(.7+aSeed.y*.11);
    float perspective=7.8/(8.5-p.z);
    float scale=min(uRes.x/9.0,uRes.y/7.5);
    vec2 clip=p.xy*perspective*scale/uRes*2.;
    gl_Position=vec4(clip,clamp(-p.z/12.,-.9,.9),1.);
    float light=clamp(dot(n,normalize(vec3(-.4,.7,1.))),0.,1.);
    float rim=pow(1.-abs(n.z),2.);
    float band=.5+.5*sin(aSeed.x*1.7+uTime*.22);
    vec3 shadow=mix(vec3(.05,.15,.18),vec3(.12,.20,.34),uDark);
    vec3 teal=mix(vec3(.15,.47,.47),vec3(.34,.77,.78),uDark);
    vec3 violet=mix(vec3(.49,.32,.67),vec3(.69,.59,.92),uDark);
    vec3 warm=mix(vec3(.84,.36,.23),vec3(1.,.62,.42),uDark);
    vec3 tint=mix(teal,violet,smoothstep(.15,.85,band));
    tint=mix(tint,warm,pow(.5+.5*sin(aSeed.x-.8),12.)*.9);
    vColor=mix(shadow,tint,.3+light*.7)+rim*.12+influence*.12;
    vAlpha=mix(.82,1.,light);
    gl_PointSize=clamp((2.0+light*1.2+rim*.6)*uDpr*perspective,1.,4.5*uDpr);
  }`;
  const fragment = `precision mediump float; varying vec3 vColor; varying float vAlpha;
  void main(){vec2 p=abs(gl_PointCoord-.5);float edge=1.-smoothstep(.36,.5,max(p.x,p.y));
  gl_FragColor=vec4(vColor,vAlpha*edge);}`;
  let program, locations, count;
  function shader(type, source) {
    const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);
    if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error('Sculpture shader unavailable');
    return s;
  }
  function initialize() {
    program=gl.createProgram();
    gl.attachShader(program,shader(gl.VERTEX_SHADER,vertex));gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fragment));
    gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error('Sculpture program unavailable');
    gl.useProgram(program);
    const data=[];const tau=Math.PI*2;
    for(let i=0;i<380;i++) {
      const t=i/380*tau,r=2+Math.cos(3*t),a=2*t;
      const c=[r*Math.cos(a),r*Math.sin(a),Math.sin(3*t)];
      const d=[-3*Math.sin(3*t)*Math.cos(a)-2*r*Math.sin(a),-3*Math.sin(3*t)*Math.sin(a)+2*r*Math.cos(a),3*Math.cos(3*t)];
      const dl=Math.hypot(...d);for(let k=0;k<3;k++)d[k]/=dl;
      const nl=Math.hypot(d[0],d[1]),normal=[d[1]/nl,-d[0]/nl,0];
      const bin=[-d[2]*normal[1],d[2]*normal[0],d[0]*normal[1]-d[1]*normal[0]];
      for(let j=0;j<56;j++) {
        const v=j/56*tau,cs=Math.cos(v),sn=Math.sin(v);
        const n=normal.map((x,k)=>x*cs+bin[k]*sn);
        const knot=c.map((x,k)=>x+n[k]*.43);
        const strand=Math.floor(j/(56/3)),side=strand-1,progress=(t/Math.PI-1);
        const split=Math.sin(t/2)*1.8;
        const fork=[progress*3.25,side*split+cs*.12,Math.cos(t*1.3+strand)*.7+sn*.12];
        const ring=2.4+cs*.24;
        const orbit=[Math.cos(t)*ring,Math.sin(t)*ring*.67+sn*.28,Math.sin(t)*ring*.6+cs*.15];
        data.push(...knot,...fork,...orbit,...n,t,v);
      }
    }
    count=data.length/14;
    const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.STATIC_DRAW);
    let offset=0;
    for(const [name,size] of [['aKnot',3],['aFork',3],['aOrbit',3],['aNormal',3],['aSeed',2]]){
      const loc=gl.getAttribLocation(program,name);gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,size,gl.FLOAT,false,56,offset*4);offset+=size;
    }
    locations=Object.fromEntries(['uMorph','uRes','uPointer','uTrail','uTrailW','uTime','uYaw','uPitch','uBurst','uDpr','uDark','uActive'].map(k=>[k,gl.getUniformLocation(program,k)]));
    gl.enable(gl.BLEND);gl.blendFuncSeparate(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA,gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.enable(gl.DEPTH_TEST);
    gl.clearColor(0,0,0,0);
  }
  const clamp=(value,min,max)=>value<min?min:value>max?max:value;
  const clampPitch=value=>clamp(value,-1.15,1.15);
  let width=1,height=1,dpr=1,time=0,spin=0,last=null,frame=null,visible=true,paused=motion.matches,lost=false;
  let morph=[1,0,0],target=[1,0,0],burst=0,px=0,py=0,tx=0,ty=0,active=0,inside=false;
  // Whole-object pose is auto yaw plus eased hover offsets plus direct drag/keyboard rotation.
  let hoverYaw=0,hoverPitch=0,hoverYawTarget=0,hoverPitchTarget=0,userYaw=0,userPitch=0;
  let spinVelYaw=0,spinVelPitch=0;
  let dragging=false,activePointer=null,dragMoved=false,dragDistance=0,dragX=0,dragY=0,dragStart=0,dragStamp=0;
  // Short cursor history gives pointer motion a small local wake that decays away.
  const trail=[[0,0,0],[0,0,0],[0,0,0]],trailXY=new Float32Array(6),trailWeight=new Float32Array(3);
  let trailHead=0;
  const MAX_YAW_VELOCITY=4,MAX_PITCH_VELOCITY=2.5,TAP_DURATION=500;
  function pose(){return [spin*.18-.30+hoverYaw+userYaw,clamp(-.38+hoverPitch+userPitch,-1.25,1.25)];}
  function stop(){if(frame!==null)cancelAnimationFrame(frame);frame=null;last=null;}
  function pushTrail(x,y,weight){trail[trailHead][0]=x;trail[trailHead][1]=y;trail[trailHead][2]=weight;trailHead=(trailHead+1)%3;}
  function clearTrail(){for(const t of trail)t[2]=0;}
  function decayTrail(dt){const k=Math.exp(-dt*3.4);for(const t of trail){t[2]*=k;if(t[2]<.004)t[2]=0;}}
  function render(){
    if(lost)return;
    gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
    const [yaw,pitch]=pose();
    gl.uniform3fv(locations.uMorph,morph);gl.uniform2f(locations.uRes,width,height);gl.uniform2f(locations.uPointer,px,py);
    for(let i=0;i<3;i++){trailXY[i*2]=trail[i][0];trailXY[i*2+1]=trail[i][1];trailWeight[i]=trail[i][2];}
    gl.uniform2fv(locations.uTrail,trailXY);gl.uniform1fv(locations.uTrailW,trailWeight);
    for(const [key,value] of Object.entries({uTime:time,uYaw:yaw,uPitch:pitch,uBurst:burst,uDpr:dpr,uDark:document.documentElement.dataset.theme==='dark'?1:0,uActive:active}))gl.uniform1f(locations[key],value);
    gl.drawArrays(gl.POINTS,0,count);
  }
  function tick(stamp){
    frame=null;if(paused||lost||!visible||document.hidden)return;
    const dt=last===null?0:Math.min((stamp-last)/1000,.05);last=stamp;time+=dt;spin+=dt;
    const ease=1-Math.exp(-dt*5);
    morph=morph.map((x,i)=>x+(target[i]-x)*ease);px+=(tx-px)*ease;py+=(ty-py)*ease;active+=((inside?1:0)-active)*ease;
    const poseEase=1-Math.exp(-dt*4);
    hoverYaw+=(hoverYawTarget-hoverYaw)*poseEase;hoverPitch+=(hoverPitchTarget-hoverPitch)*poseEase;
    if(!dragging){
      userYaw+=spinVelYaw*dt;userPitch=clampPitch(userPitch+spinVelPitch*dt);
      const damp=Math.exp(-dt*2.6);spinVelYaw*=damp;spinVelPitch*=damp;
      if(Math.abs(spinVelYaw)<.02)spinVelYaw=0;
      if(Math.abs(spinVelPitch)<.02)spinVelPitch=0;
    }
    burst*=Math.exp(-dt*2.6);decayTrail(dt);render();frame=requestAnimationFrame(tick);
  }
  function start(){if(frame===null&&!paused&&!lost&&visible&&!document.hidden){last=null;frame=requestAnimationFrame(tick);}}
  function resize(){const box=canvas.getBoundingClientRect();width=Math.max(1,box.width);height=Math.max(1,box.height);dpr=Math.min(devicePixelRatio||1,2);canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);gl.viewport(0,0,canvas.width,canvas.height);render();}
  function label(){pause.textContent=paused?'播放动态 ↗':'暂停动态 Ⅱ';pause.setAttribute('aria-pressed',String(paused));}
  function pulse(){
    if(paused){burst=burst>.1?0:1.5;render();status.textContent=burst?'散开静帧；再次点冲散可归位。':'已回到完整形态。';}
    else{burst=2.0;status.textContent='粒子散开后自动归位。';}
  }
  function stageControls(enabled){
    if(enabled){stage.setAttribute('tabindex','0');stage.setAttribute('role','group');stage.setAttribute('aria-label','原创粒子作品：拖动旋转，方向键调整姿态，Home 复位');}
    else for(const name of ['tabindex','role','aria-label'])stage.removeAttribute(name);
  }
  function showFallback(){lost=true;stop();endDrag();clearTrail();stageControls(false);canvas.hidden=true;fallback.removeAttribute('hidden');controls.hidden=true;hint.hidden=true;pause.hidden=true;status.textContent='动态图形暂不可用，显示静态作品。';}
  function isNestedControl(target){return !!(target&&typeof target.closest==='function'&&target.closest('a,button,input,select,textarea,[role="button"]'));}
  function localPoint(event){const box=canvas.getBoundingClientRect(),scale=Math.min(width/9,height/7.5);return {x:(event.clientX-box.left-width/2)/scale,y:-(event.clientY-box.top-height/2)/scale,nx:(event.clientX-box.left)/width-.5,ny:(event.clientY-box.top)/height-.5};}
  function hoverAt(event){const p=localPoint(event);tx=p.x;ty=p.y;inside=true;hoverYawTarget=-p.nx*.6;hoverPitchTarget=-p.ny*.4;pushTrail(p.x,p.y,1);}
  function dragTo(event){
    const dx=event.clientX-dragX,dy=event.clientY-dragY;dragX=event.clientX;dragY=event.clientY;
    dragDistance+=Math.hypot(dx,dy);if(dragDistance>6)dragMoved=true;
    userYaw+=dx*.006;userPitch=clampPitch(userPitch+dy*.005);
    const stamp=typeof event.timeStamp==='number'?event.timeStamp:dragStamp+16;
    const dtMove=clamp((stamp-dragStamp)/1000,1/240,.05);dragStamp=stamp;
    spinVelYaw=clamp(spinVelYaw*.5+(dx*.006)/dtMove*.5,-MAX_YAW_VELOCITY,MAX_YAW_VELOCITY);
    spinVelPitch=clamp(spinVelPitch*.5+(dy*.005)/dtMove*.5,-MAX_PITCH_VELOCITY,MAX_PITCH_VELOCITY);
    if(paused)render();
  }
  function endDrag(event){
    if(event?.pointerId!=null&&event.pointerId!==activePointer)return;
    const id=activePointer;activePointer=null;dragging=false;dragMoved=false;spinVelYaw=0;spinVelPitch=0;
    stage.removeAttribute('data-dragging');releaseCapture(id);
  }
  function releaseCapture(pointerId){if(stage.releasePointerCapture&&pointerId!=null){try{stage.releasePointerCapture(pointerId);}catch(_){}}}
  function resetPose(){
    endDrag();spin=0;burst=0;active=0;inside=false;px=py=tx=ty=0;morph=[...target];
    userYaw=0;userPitch=0;hoverYaw=0;hoverPitch=0;hoverYawTarget=0;hoverPitchTarget=0;
    clearTrail();status.textContent='当前形态已回到初始视角。';render();
  }
  function pointerDown(event){
    if(dragging||event.isPrimary===false||(typeof event.button==='number'&&event.button!==0))return;
    if(isNestedControl(event.target))return;
    dragging=true;activePointer=event.pointerId;dragMoved=false;dragDistance=0;dragX=event.clientX;dragY=event.clientY;
    stage.setAttribute('data-dragging','');
    dragStamp=dragStart=typeof event.timeStamp==='number'?event.timeStamp:0;
    spinVelYaw=0;spinVelPitch=0;hoverYawTarget=0;hoverPitchTarget=0;
    if(stage.setPointerCapture&&event.pointerId!=null){try{stage.setPointerCapture(event.pointerId);}catch(_){}}
  }
  function pointerMove(event){
    if(event.isPrimary===false)return;
    if(dragging){if(event.pointerId===activePointer)dragTo(event);return;}
    if(paused)return; // Hover must not animate a paused or reduced-motion scene.
    hoverAt(event);
  }
  function pointerUp(event){
    if(dragging&&event.pointerId===activePointer&&event.isPrimary!==false){
      const clean=!dragMoved&&(typeof event.timeStamp==='number'?event.timeStamp-dragStart:0)<TAP_DURATION;
      dragging=false;activePointer=null;dragMoved=false;stage.removeAttribute('data-dragging');releaseCapture(event.pointerId);
      if(paused){spinVelYaw=0;spinVelPitch=0;}
      if(clean&&!isNestedControl(event.target)){inside=false;pulse();}
      return;
    }
  }
  function pointerLeave(){if(dragging)return;inside=false;hoverYawTarget=0;hoverPitchTarget=0;}
  function keyDown(event){
    if(event.defaultPrevented||isNestedControl(event.target))return;
    const step=event.shiftKey?.12:.3;let handled=true;
    switch(event.key){
      case 'ArrowLeft':userYaw-=step;break;
      case 'ArrowRight':userYaw+=step;break;
      case 'ArrowUp':userPitch=clampPitch(userPitch-step);break;
      case 'ArrowDown':userPitch=clampPitch(userPitch+step);break;
      case 'Home':resetPose();break;
      default:handled=false;
    }
    if(!handled)return;
    if(typeof event.preventDefault==='function')event.preventDefault();
    if(paused)render();
  }
  try{initialize();}catch(_){showFallback();return;}
  pause.addEventListener('click',()=>{paused=!paused;label();if(paused)stop();else start();});
  modeButtons.forEach((button,index)=>button.addEventListener('click',()=>{
    target=[0,0,0];target[index]=1;modeButtons.forEach((b,i)=>b.setAttribute('aria-pressed',String(i===index)));
    status.textContent=['编织','分岔','环流'][index]+'形态；仅为原创视觉作品。';
    if(paused){morph=[...target];burst=0;render();}
  }));
  burstButton.addEventListener('click',pulse);
  if(resetButton)resetButton.addEventListener('click',resetPose);
  stage.addEventListener('pointerdown',pointerDown);
  stage.addEventListener('pointermove',pointerMove,{passive:true});
  stage.addEventListener('pointerup',pointerUp);
  stage.addEventListener('pointercancel',endDrag);
  stage.addEventListener('lostpointercapture',endDrag);
  stage.addEventListener('pointerleave',pointerLeave);
  stage.addEventListener('keydown',keyDown);
  motion.addEventListener('change',()=>{if(motion.matches){paused=true;stop();endDrag();active=0;burst=0;morph=[...target];hoverYawTarget=0;hoverPitchTarget=0;clearTrail();label();render();}});
  document.addEventListener('visibilitychange',()=>{if(document.hidden){stop();endDrag();inside=false;hoverYawTarget=0;hoverPitchTarget=0;}else start();});
  if(typeof window!=='undefined')window.addEventListener('blur',()=>{endDrag();inside=false;hoverYawTarget=0;hoverPitchTarget=0;});
  document.addEventListener('themechange',render);
  canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();showFallback();});
  canvas.addEventListener('webglcontextrestored',()=>{try{initialize();lost=false;stageControls(true);canvas.hidden=false;fallback.setAttribute('hidden','');controls.hidden=false;hint.hidden=false;pause.hidden=false;status.textContent="粒子作品已恢复；"+(paused?"当前已暂停。":"动态播放中。");resize();start();}catch(_){showFallback();}});
  canvas.hidden=false;fallback.setAttribute('hidden','');controls.hidden=false;hint.hidden=false;pause.hidden=false;stageControls(true);label();resize();
  new ResizeObserver(resize).observe(canvas);
  new IntersectionObserver(entries=>{visible=entries[entries.length-1].isIntersecting;if(visible)start();else{stop();endDrag();}}).observe(canvas);
  start();
})();
