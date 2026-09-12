import { createRoot } from "react-dom/client";
import "@fontsource/inter/latin-300.css";
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-500.css";
import "./styles.css";
// Loaded after the foundation so the instrument skin wins on equal specificity.
import "./theme-phosphor.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(<App />);
