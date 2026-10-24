/* No timers, dependencies or telemetry: shared navigation ergonomics. */
(()=>{'use strict';
const pickers=[...document.querySelectorAll('.project-switch')];
function closePicker(p,restore=false){p.open=false;if(restore)p.querySelector('summary')?.focus();}
pickers.forEach(p=>{p.addEventListener('toggle',()=>{if(p.open)pickers.filter(other=>other!==p).forEach(other=>closePicker(other));});p.addEventListener('keydown',e=>{if(e.key==='Escape'&&p.open){e.preventDefault();e.stopPropagation();closePicker(p,true);}});});
document.addEventListener('pointerdown',e=>pickers.forEach(p=>{if(p.open&&!p.contains(e.target))closePicker(p);}));
document.addEventListener('focusin',e=>pickers.forEach(p=>{if(p.open&&!p.contains(e.target))closePicker(p);}));
const visibility=()=>document.body.classList.toggle('finish-hidden',document.hidden);document.addEventListener('visibilitychange',visibility);visibility();
})();
