import 'pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css';
import './app.css';
import { mount } from 'svelte';
import App from './App.svelte';
import ButtonTest from './lib/components/ButtonTest.svelte';

// ?buttons: the handset button test page instead of the kiosk (no backend, no conversation).
const page = new URLSearchParams(location.search).has('buttons') ? ButtonTest : App;
const app = mount(page, { target: document.getElementById('app')! });

export default app;
