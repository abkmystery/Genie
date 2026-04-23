import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import GuidanceOverlay from "./GuidanceOverlay";
import RegionOverlay from "./RegionOverlay";
import "./styles/app.css";

const searchParams = new URLSearchParams(window.location.search);
const overlayMode = searchParams.get("overlay");

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {overlayMode === "region" ? <RegionOverlay /> : overlayMode === "guidance" ? <GuidanceOverlay /> : <App />}
  </StrictMode>,
);
