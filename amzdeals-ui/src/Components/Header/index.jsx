import React from 'react'
import { RiPriceTag3Line } from "react-icons/ri";
import { IoIosSearch } from 'react-icons/io'
import Button from '@mui/material/Button'
import { NavLink } from 'react-router-dom';

export default function Header() {
  return (
    <div className="row header d-flex align-items-center">
        <div className="col-sm-2 d-flex align-items-center">
            <span className="ms-4"><RiPriceTag3Line className="bg-pricetag"/></span>
            <h3 className="header-title">dealwise</h3>
        </div>
        <div className="col-sm-6 d-flex justify-content-center">
            <div className="headerSearch ml-3 mr-3">
              <Button><IoIosSearch /></Button>
              <input type="text" placeholder="Search for product, brand" />  
            </div>
        </div>
        <div className="col-sm-4 d-flex align-items-center">
            <nav class="navbar navbar-expand-lg">
              <div class="container-fluid">
                <div class="collapse navbar-collapse" id="navbarNav">
                  <ul class="navbar-nav">
                    <li class="nav-item">
                      <NavLink className="nav-link" aria-current="page" to="/">Home</NavLink>
                    </li>
                    <li class="nav-item">
                      <NavLink className="nav-link" to="/find-deal">Find a deal</NavLink>
                    </li>
                    <li class="nav-item">
                      <NavLink className="nav-link" to="/top-deals">Top Deals</NavLink>
                    </li>
                  </ul>
                </div>
              </div>
            </nav>
        </div>
    </div>
  )
}
