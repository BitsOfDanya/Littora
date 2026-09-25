const THEME_BOOTSTRAP = `try{var s=JSON.parse(localStorage.getItem("littora.preferences")||"null");var t=s&&s.state&&s.state.theme;if(t==="day"||t==="night")document.documentElement.dataset.theme=t}catch(e){}`;

export function ThemeScript() {
  return <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />;
}
