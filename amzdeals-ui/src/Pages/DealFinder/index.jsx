import React from 'react'
import { FaCheck } from "react-icons/fa6";
import { IoIosSearch } from 'react-icons/io';
import Button from '@mui/material/Button';
import RadioGroup from '@mui/material/RadioGroup';
import FormControlLabel from '@mui/material/FormControlLabel';
import Radio from '@mui/material/Radio';
import { styled } from '@mui/material/styles';

import RangeSlider from 'react-range-slider-input';
import 'react-range-slider-input/dist/style.css';
import FormControl from '@mui/material/FormControl';

import CurrencyInput from 'react-currency-input-field';
import FormGroup from '@mui/material/FormGroup';
import Checkbox from '@mui/material/Checkbox';
import ButtonGroup from '@mui/material/ButtonGroup';

import { FiGrid } from "react-icons/fi";
import { IoIosList } from "react-icons/io";
import Pagination from '@mui/material/Pagination';

export default function DealFinder() {

  const BpIcon = styled('span')(({ theme }) => ({
    borderRadius: '50%',
    width: 16,
    height: 16,
    boxShadow: 'inset 0 0 0 1px rgba(16,22,26,.2), inset 0 -1px 0 rgba(16,22,26,.1)',
    backgroundColor: '#f5f8fa',
    backgroundImage: 'linear-gradient(180deg,hsla(0,0%,100%,.8),hsla(0,0%,100%,0))',
    '.Mui-focusVisible &': {
      outline: '2px auto rgba(19,124,189,.6)',
      outlineOffset: 2,
    },
    'input:hover ~ &': {
      backgroundColor: '#ebf1f5',
      ...theme.applyStyles('dark', {
        backgroundColor: '#30404d',
      }),
    },
    'input:disabled ~ &': {
      boxShadow: 'none',
      background: 'rgba(206,217,224,.5)',
      ...theme.applyStyles('dark', {
        background: 'rgba(57,75,89,.5)',
      }),
      '@media (forced-colors: active)': {
        outline: '1px solid GrayText',
      },
    },
    '@media (forced-colors: active)': {
      outline: '1px solid ButtonText',
    },
    ...theme.applyStyles('dark', {
      boxShadow: '0 0 0 1px rgb(16 22 26 / 40%)',
      backgroundColor: '#394b59',
      backgroundImage: 'linear-gradient(180deg,hsla(0,0%,100%,.05),hsla(0,0%,100%,0))',
    }),
  }));

  const BpCheckedIcon = styled(BpIcon)({
    backgroundColor: '#237a50',
    backgroundImage: 'linear-gradient(180deg,hsla(0,0%,100%,.1),hsla(0,0%,100%,0))',
    '&::before': {
      display: 'block',
      width: 16,
      height: 16,
      backgroundImage: 'radial-gradient(#fff,#fff 28%,transparent 32%)',
      content: '""',
      '@media (forced-colors: active)': {
        backgroundImage: 'none',
        backgroundColor: 'ButtonText',
        borderRadius: '50%',
        width: 8,
        height: 8,
        margin: 4,
      },
    },
    'input:hover ~ &': {
      backgroundColor: '#106ba3',
    },
    '@media (forced-colors: active)': {
      outline: '2px solid ButtonText',
    },
  });

  const [value, setValue] = React.useState([0, 50000]);

  return (
    <>
      <div className="container dealListing">
        <div className="row mt-4">
          <h3 className="deal-finder-head px-0">Find your next great deal.</h3>
          <span className="ml-30 px-0">Search smarter. Compare prices. Save on the things you love.</span>
        </div>
        <div className="row productSearch">
          <div className="col-sm-8 px-0">
            <form>
              <IoIosSearch />
              <input className="pd-20" type="text" placeholder="Search products, brands or stores" />
              <Button>Search deals</Button>
            </form>
          </div>
          <div className="col-sm-3 ms-2">
            <div className="alert alert-success compare-banner text-center" role="alert">
              <FaCheck /> Compare! Don't overpay.
            </div>
          </div>
        </div>
        <div className="row mt-4">
          <div className="col-sm-2 filterSection">
            <span className="filter-title">Filters</span>
            <Button className="float-end reset-btn" variant="outlined">Reset all</Button>
            <hr style={{ opacity: 0.1 }} />
            <div className="filter-categories">
              <span className="cat-title">Category</span>
              <RadioGroup sx={{ '& .MuiSvgIcon-root': { fontSize: 14 } }} className="mt-2">
                <FormControlLabel value="female" control={<Radio icon={<BpIcon />} checkedIcon={<BpCheckedIcon />} />} label="Female" />
                <FormControlLabel value="male" control={<Radio icon={<BpIcon />} checkedIcon={<BpCheckedIcon />} />} label="Male" />
                <FormControlLabel value="other" control={<Radio icon={<BpIcon />} checkedIcon={<BpCheckedIcon />} />} label="Other" />
                <FormControlLabel value="other1" control={<Radio icon={<BpIcon />} checkedIcon={<BpCheckedIcon />} />} label="Other" />
                <FormControlLabel value="other2" control={<Radio icon={<BpIcon />} checkedIcon={<BpCheckedIcon />} />} label="Other" />
              </RadioGroup>
            </div>
            <hr style={{ opacity: 0.1 }} />
            <div className="filter-price mt-2">
              <span className="cat-title">Price Range</span>
              <div className="d-flex justify-content-center mt-2">
                <CurrencyInput className="price-range" value={value[0]} prefix="₹" onValueChange={(value) => setValue([value, value[1]])} />
                <span className="px-2">-</span>
                <CurrencyInput className="price-range" value={value[1]} prefix="₹" onValueChange={(value) => setValue([value[0], value])} />
              </div>
              <RangeSlider
                min={0}
                max={50000}
                step={100}
                value={value}
                onInput={setValue}
                className="mt-3"
              />
            </div>
            <hr style={{ opacity: 0.1 }} />
            <div className="filter-discounts mt-3">
              <span className="cat-title">Discount</span>
              <RadioGroup sx={{ '& .MuiSvgIcon-root': { fontSize: 14 } }} className="mt-2">
                <FormControlLabel value="Any Discount" control={<Radio icon={<BpIcon />} checkedIcon={<BpCheckedIcon />} />} label="Any Discount" />
                <FormControlLabel value="10-25" control={<Radio icon={<BpIcon />} checkedIcon={<BpCheckedIcon />} />} label="10% or more" />
                <FormControlLabel value="25-50" control={<Radio icon={<BpIcon />} checkedIcon={<BpCheckedIcon />} />} label="25% or more" />
                <FormControlLabel value="50+" control={<Radio icon={<BpIcon />} checkedIcon={<BpCheckedIcon />} />} label="50% or more" />
              </RadioGroup>
            </div>
            <hr style={{ opacity: 0.1 }} />
            <div className="filter-ratings mt-3">
              <span className="cat-title">Ratings</span>
              <div>
                <FormControl component="fieldset">
                  <FormGroup>
                    <FormControlLabel
                      control={<Checkbox name="gilad" size='small' color="success" />}
                      label="Gilad Gray"
                    />
                    <FormControlLabel
                      control={<Checkbox name="jason" size='small' color="success" />}
                      label="Jason Killian"
                    />
                  </FormGroup>
                </FormControl>
              </div>
            </div>
            <hr style={{ opacity: 0.1 }} />
          </div>
          <div className="col-sm-9 dealListingSection">
            <div class="row d-flex align-items-center">
              <div className="d-flex col-sm-6">
                <h4>All deals</h4>
                <p className="ms-2 result-span">128 results</p>
              </div>
              <div className="col-sm-6">
                <ButtonGroup size="small" variant="contained" aria-label="outlined button group" className="sort-btn float-end">
                  <Button className="bg-white no-border"><FiGrid className="text-dark" /></Button>
                  <Button className="bg-white"><IoIosList className="text-dark" /></Button>
                </ButtonGroup>
              </div>
            </div>
            <div className="row d-flex align-items-center dealListing mt-3">
              <div className="card col-sm-4">
                <img src="..." class="card-img-top" alt="..." />
                <div className="card-body">
                  <h5 className="card-title">Card title</h5>
                  <p className="card-text">Some quick example text</p>
                  <Button className="btn btn-primary">Go somewhere</Button>
                </div>
              </div>
              <div className="card col-sm-4">
                <img src="..." class="card-img-top" alt="..." />
                <div className="card-body">
                  <h5 className="card-title">Card title</h5>
                  <p className="card-text">Some quick example text</p>
                  <Button href="#" className="btn btn-primary">Go somewhere</Button>
                </div>
              </div>
              <div className="card col-sm-4">
                <img src="..." class="card-img-top" alt="..." />
                <div className="card-body">
                  <h5 className="card-title">Card title</h5>
                  <p className="card-text">Some quick example text</p>
                  <Button href="#" className="btn btn-primary">Go somewhere</Button>
                </div>
              </div>
              <div className="card col-sm-4">
                <img src="..." class="card-img-top" alt="..." />
                <div className="card-body">
                  <h5 className="card-title">Card title</h5>
                  <p className="card-text">Some quick example text</p>
                  <Button className="btn btn-primary">Go somewhere</Button>
                </div>
              </div>
              <div className="card col-sm-4">
                <img src="..." class="card-img-top" alt="..." />
                <div className="card-body">
                  <h5 className="card-title">Card title</h5>
                  <p className="card-text">Some quick example text</p>
                  <Button href="#" className="btn btn-primary">Go somewhere</Button>
                </div>
              </div>
              <div className="card col-sm-4">
                <img src="..." class="card-img-top" alt="..." />
                <div className="card-body">
                  <h5 className="card-title">Card title</h5>
                  <p className="card-text">Some quick example text</p>
                  <Button href="#" className="btn btn-primary">Go somewhere</Button>
                </div>
              </div>
              <div className="card col-sm-4">
                <img src="..." class="card-img-top" alt="..." />
                <div className="card-body">
                  <h5 className="card-title">Card title</h5>
                  <p className="card-text">Some quick example text</p>
                  <Button className="btn btn-primary">Go somewhere</Button>
                </div>
              </div>
              <div className="card col-sm-4">
                <img src="..." class="card-img-top" alt="..." />
                <div className="card-body">
                  <h5 className="card-title">Card title</h5>
                  <p className="card-text">Some quick example text</p>
                  <Button href="#" className="btn btn-primary">Go somewhere</Button>
                </div>
              </div>
              <div className="card col-sm-4">
                <img src="..." class="card-img-top" alt="..." />
                <div className="card-body">
                  <h5 className="card-title">Card title</h5>
                  <p className="card-text">Some quick example text</p>
                  <Button href="#" className="btn btn-primary">Go somewhere</Button>
                </div>
              </div>
              <div className="card col-sm-4">
                <img src="..." class="card-img-top" alt="..." />
                <div className="card-body">
                  <h5 className="card-title">Card title</h5>
                  <p className="card-text">Some quick example text</p>
                  <Button className="btn btn-primary">Go somewhere</Button>
                </div>
              </div>
              <div className="card col-sm-4">
                <img src="..." class="card-img-top" alt="..." />
                <div className="card-body">
                  <h5 className="card-title">Card title</h5>
                  <p className="card-text">Some quick example text</p>
                  <Button href="#" className="btn btn-primary">Go somewhere</Button>
                </div>
              </div>
              <div className="card col-sm-4">
                <img src="..." class="card-img-top" alt="..." />
                <div className="card-body">
                  <h5 className="card-title">Card title</h5>
                  <p className="card-text">Some quick example text</p>
                  <Button href="#" className="btn btn-primary">Go somewhere</Button>
                </div>
              </div>
            </div>
            <span className="result-text float-start">Showing results 1-12 of 128 deals</span>
            <Pagination count={10} variant="outlined" shape="rounded" className="float-end mt-3 page-buttons" color='primary'/>
          </div>
        </div>
      </div>
    </>
  )
}
