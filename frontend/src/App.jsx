// frontend/src/App.jsx
import React from 'react';
import Chat from './components/Chat';
import './App.css';

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>Palona Shop</h1>
      </header>
      
      <main className="main-container">
        <Chat  />
      </main>
    </div>
  );
}

export default App;