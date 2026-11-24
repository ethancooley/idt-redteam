import { NavLink, Route, Routes } from "react-router-dom";
import { Admin } from "./pages/Admin";
import { Attacks } from "./pages/Attacks";
import { CasePage } from "./pages/CasePage";
import { Home } from "./pages/Home";
import { Lab } from "./pages/Lab";
import { Method } from "./pages/Method";

export function App() {
  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <header className="site">
        <NavLink to="/" className="brand" end>Planted notes</NavLink>
        <nav aria-label="Main">
          <NavLink to="/" end>Results</NavLink>
          <NavLink to="/attacks">The attacks</NavLink>
          <NavLink to="/lab">Attack lab</NavLink>
          <NavLink to="/method">Method</NavLink>
        </nav>
      </header>
      <main id="main">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/attacks" element={<Attacks />} />
          <Route path="/case/:id" element={<CasePage />} />
          <Route path="/lab" element={<Lab />} />
          <Route path="/method" element={<Method />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="*" element={<p>That page doesn't exist. <NavLink to="/">Go to the results</NavLink></p>} />
        </Routes>
      </main>
      <footer className="site">
        <p>
          A red-teaming study of <a href="https://idt.ethancooley.com">IDT Prep Copilot</a> for Duke AIPI's
          Responsible AI course. Every participant, note, and clinician here is synthetic.{" "}
          <a href="/poster.pdf">Download the poster (PDF)</a>.
        </p>
      </footer>
    </>
  );
}
