import React from 'react'
import { FaCheck } from "react-icons/fa6";

export default function DealFinder() {
  return (
    <>
     <div className="container">
       <div className="row mt-4">
         <h3 className="deal-finder-head px-0">Find your next great deal.</h3>
         <span className="ml-30 px-0">Search smarter. Compare prices. Save on the things you love.</span>
       </div>
       <div className="row productSearch">
         <div className="col-sm-8 px-0">
            <input className="pd-20" type="text" placeholder="Search products, brands or stores" />
         </div>
         <div className="col-sm-3 ms-2">
            <div className="alert alert-success compare-banner text-center" role="alert">
              <FaCheck /> Compare! Don't overpay.
            </div>
         </div>
       </div>
      </div>
    </>
  )
}
