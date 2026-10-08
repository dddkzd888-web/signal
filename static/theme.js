(()=>{
  let theme='dark';
  try{theme=localStorage.getItem('signal-desk-theme')==='light'?'light':'dark';}catch{}
  const apply=value=>{
    theme=value;
    document.documentElement.dataset.theme=theme;
    const meta=document.querySelector('meta[name="theme-color"]');
    if(meta)meta.content=theme==='light'?'#eef5fa':'#101419';
    const button=document.getElementById('themeToggle');
    if(button){button.textContent=theme==='light'?'☾ 夜间模式':'☀ 白天模式';button.setAttribute('aria-pressed',String(theme==='light'));}
    document.dispatchEvent(new Event('themechange'));
  };
  apply(theme);
  document.addEventListener('DOMContentLoaded',()=>{
    apply(theme);
    document.getElementById('themeToggle').addEventListener('click',()=>{
      apply(theme==='light'?'dark':'light');
      try{localStorage.setItem('signal-desk-theme',theme);}catch{}
    });
  });
})();
