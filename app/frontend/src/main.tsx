import React from 'react';
import ReactDOM from 'react-dom/client';

import App from './App';
import './styles.css';

const PRODUCT_ID = 'aeris-everyday-tee';
const container = document.getElementById('root');

if (!container) {
  throw new Error('Root container #root is missing from index.html');
}

ReactDOM.createRoot(container).render(
  <React.StrictMode>
    <App productId={PRODUCT_ID} />
  </React.StrictMode>,
);
