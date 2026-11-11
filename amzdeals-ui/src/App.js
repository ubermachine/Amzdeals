import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Home from './Pages/Home';
import Header from './Components/Header';
import DealFinder from './Pages/DealFinder';
import TopDeals from './Pages/TopDeals';
import './App.css';

function App() {
  return (
    <BrowserRouter>
        <Header />
        <Routes>
          <Route path="/" exact={true} element={<Home />} />
          <Route path="/find-deal" element={<DealFinder />} />
          <Route path="/top-deals" element={<TopDeals />} />
        </Routes>
    </BrowserRouter>
  );
}

export default App;
