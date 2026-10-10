import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Check, ChevronDown, Grid2X2, Home, Menu, Minus, Plus, Search, ShoppingBag, Sparkles, Store, Truck, UserRound, X } from 'lucide-react'
import { supabase } from './supabase'
import { api } from './api'

const defaultCats = [{id:'all',name:'All styles',slug:'all'},...['Women','Men','Kids','Ethnic Wear','Accessories'].map((name,i)=>({id:name.toLowerCase(),name,slug:['women','men','kids','ethnic-wear','accessories'][i]}))]
const money = n => `₹${Number(n||0).toLocaleString('en-IN',{maximumFractionDigits:2})}`

export default function App() {
 const [session,setSession]=useState(null),[profile,setProfile]=useState(null)
 const [products,setProducts]=useState([]),[categories,setCategories]=useState(defaultCats)
 const [loading,setLoading]=useState(true),[error,setError]=useState(''),[search,setSearch]=useState(''),[category,setCategory]=useState('all')
 const [cart,setCart]=useState([]),[selected,setSelected]=useState(null),[size,setSize]=useState(''),[color,setColor]=useState('')
 const [drawer,setDrawer]=useState(''),[menu,setMenu]=useState(false),[toast,setToast]=useState(''),[orders,setOrders]=useState([])
 const [busy,setBusy]=useState(false),[mobileActive,setMobileActive]=useState('home'),searchInputRef=useRef(null),[address,setAddress]=useState({recipient_name:'',phone:'',line1:'',line2:'',landmark:'',city:'Rayachoty',state:'Andhra Pradesh',postal_code:'',notes:''})
 const [productForm,setProductForm]=useState({name:'',description:'',price:'',compare_at_price:'',category_id:'',vendor_id:'',image_url:'',image_public_id:'',sizes:'S,M,L,XL',colors:'Black,Blue',stock_quantity:'1'})
 const [categoryForm,setCategoryForm]=useState({category_id:'',image_url:''})
 useEffect(()=>{if(!supabase)return;supabase.auth.getSession().then(({data})=>setSession(data.session));const {data}=supabase.auth.onAuthStateChange((_,s)=>{setSession(s);if(!s)setProfile(null)});return()=>data.subscription.unsubscribe()},[])
 useEffect(()=>{if(!session){setProfile(null);return}api('/profile/',{token:session.access_token}).then(setProfile).catch(()=>setProfile({role:'customer'}))},[session])
 useEffect(()=>{const controller=new AbortController();const timer=window.setTimeout(()=>load(controller.signal),180);return()=>{window.clearTimeout(timer);controller.abort()}},[category,search])
 async function load(signal){setLoading(true);try{const q=new URLSearchParams();if(category!=='all')q.set('category',category);if(search.trim())q.set('search',search.trim());const [p,c]=await Promise.all([api(`/products/?${q}`,{signal}),api('/categories/',{signal}).catch(e=>{if(e.name==='AbortError')throw e;return defaultCats.slice(1)})]);setProducts(Array.isArray(p.results)?p.results:Array.isArray(p)?p:[]);setCategories([defaultCats[0],...c]);setError('')}catch(e){if(e.name!=='AbortError'){setProducts([]);setError('We could not load the live catalog. Check your connection and try again.')}}finally{if(!signal?.aborted)setLoading(false)}}
 function notify(t){setToast(t);window.setTimeout(()=>setToast(''),2600)}
 async function login(){if(!supabase)return notify('Set Supabase frontend environment variables first.');const {error}=await supabase.auth.signInWithOAuth({provider:'google',options:{redirectTo:location.origin}});if(error)notify(error.message)}
 async function logout(){await supabase?.auth.signOut();setDrawer('');notify('Signed out')}
 const count=cart.reduce((n,p)=>n+p.quantity,0),subtotal=cart.reduce((n,p)=>n+Number(p.price)*p.quantity,0)
 const vendors=[...new Set(cart.map(p=>p.vendor_id||p.vendor_name))]
 function add(p,s=p.sizes?.[0]||'',c=p.colors?.[0]||''){const stock=Number(p.stock_quantity??p.stock??0);if(!Number.isFinite(stock)||stock<1){notify('This item is currently unavailable.');return}const key=`${p.id}:${s}:${c}`;setCart(old=>old.some(i=>i.key===key)?old.map(i=>i.key===key?{...i,quantity:Math.min(i.quantity+1,stock)}:i):[...old,{...p,key,quantity:1,size:s,color:c}]);setSelected(null);setDrawer('cart');notify('Added to your bag')}
 async function getOrders(){if(!session)return login();try{const r=await api('/orders/',{token:session.access_token});setOrders(r.results||r);setDrawer('orders')}catch(e){notify(e.message)}}
 async function uploadImage(file){
  if(!file||!session)return notify('Sign in with an approved vendor/admin account first.')
  setBusy(true)
  try{
   const sign=await api('/uploads/signature/',{method:'POST',token:session.access_token,body:JSON.stringify({folder:'bala-fashion/products'})})
   const form=new FormData()
   Object.entries(sign.params).forEach(([k,v])=>form.append(k,v))
   form.append('api_key',sign.api_key);form.append('signature',sign.signature);form.append('file',file)
   const response=await fetch(`https://api.cloudinary.com/v1_1/${sign.cloud_name}/image/upload`,{method:'POST',body:form})
   const data=await response.json()
   if(!response.ok)throw new Error(data.error?.message||'Cloudinary upload failed')
   setProductForm(p=>({...p,image_url:data.secure_url,image_public_id:data.public_id}))
   notify('Image uploaded to Cloudinary')
  }catch(e){notify(e.message)}finally{setBusy(false)}
 }
 async function uploadCategoryImage(file){
  if(!file||!session)return notify('Sign in with an admin account first.')
  if(!file.type.startsWith('image/'))return notify('Choose an image file.')
  if(file.size>8*1024*1024)return notify('Choose an image smaller than 8 MB.')
  setBusy(true)
  try{
   const sign=await api('/uploads/signature/',{method:'POST',token:session.access_token,body:JSON.stringify({folder:'bala-fashion/categories'})})
   const form=new FormData()
   Object.entries(sign.params).forEach(([k,v])=>form.append(k,v))
   form.append('api_key',sign.api_key);form.append('signature',sign.signature);form.append('file',file)
   const response=await fetch(`https://api.cloudinary.com/v1_1/${sign.cloud_name}/image/upload`,{method:'POST',body:form})
   const data=await response.json()
   if(!response.ok)throw new Error(data.error?.message||'Cloudinary upload failed')
   setCategoryForm(p=>({...p,image_url:data.secure_url}))
   notify('Category image uploaded')
  }catch(e){notify(e.message)}finally{setBusy(false)}
 }
 async function saveCategoryImage(e){
  e.preventDefault();if(busy)return;if(!session)return login()
  if(!categoryForm.category_id)return notify('Choose a category first.')
  if(!categoryForm.image_url)return notify('Upload a category image first.')
  setBusy(true)
  try{
   await api('/categories/manage/',{method:'PATCH',token:session.access_token,body:JSON.stringify(categoryForm)})
   await load();setDrawer('');notify('Category image saved')
  }catch(e){notify(e.message)}finally{setBusy(false)}
 }
 async function saveProduct(e){
  e.preventDefault();if(busy)return;if(!session)return login();setBusy(true)
  try{
   await api('/products/manage/',{method:'POST',token:session.access_token,body:JSON.stringify({...productForm,price:Number(productForm.price),compare_at_price:productForm.compare_at_price?Number(productForm.compare_at_price):null,stock_quantity:Number(productForm.stock_quantity),sizes:productForm.sizes.split(',').map(x=>x.trim()).filter(Boolean),colors:productForm.colors.split(',').map(x=>x.trim()).filter(Boolean)})})
   setProductForm({name:'',description:'',price:'',compare_at_price:'',category_id:'',vendor_id:'',image_url:'',image_public_id:'',sizes:'S,M,L,XL',colors:'Black,Blue',stock_quantity:'1'})
   await load();setDrawer('');notify('Product saved')
  }catch(e){notify(e.message)}finally{setBusy(false)}
 }
 async function place(e){e.preventDefault();if(busy)return;if(!session)return login();if(vendors.length>1)return notify('Checkout one seller at a time.');setBusy(true);try{const r=await api('/orders/',{method:'POST',token:session.access_token,body:JSON.stringify({address,notes:address.notes,items:cart.map(i=>({product_id:i.id,quantity:i.quantity,size:i.size,color:i.color}))})});setCart([]);setOrders(o=>[r,...o]);setDrawer('orders');notify(`Order ${r.order_number} placed`)}catch(err){notify(err.message)}finally{setBusy(false)}}
 const catalogContent = <>
  {error&&<div className="notice">{error}<button onClick={()=>load(new AbortController().signal)}>Retry</button></div>}
  <div className="grid">{loading?Array.from({length:6},(_,i)=><div className="skeleton" key={i}><div/></div>):products.map((p,i)=><article className="product" key={p.id}><button className="photo" onClick={()=>{setSelected(p);setSize(p.sizes?.[0]||'');setColor(p.colors?.[0]||'')}}>{p.image_url?<img src={p.image_url} alt={p.name} loading={i>2?'lazy':'eager'} onError={e=>{e.currentTarget.style.display='none';e.currentTarget.parentElement.classList.add('image-failed')}}/>:<span className="placeholder">BF</span>}{p.compare_at_price&&Number(p.compare_at_price)>Number(p.price)&&<small className="sale">SPECIAL PRICE</small>}<span className="quick">Quick view <ArrowRight size={13}/></span></button><div className="product-info"><div className="meta"><span>{p.category_name||'Curated style'}</span><span>{p.vendor_name||'Local seller'}</span></div><button className="product-name" onClick={()=>{setSelected(p);setSize(p.sizes?.[0]||'');setColor(p.colors?.[0]||'')}}>{p.name}</button><div className="price"><b>{money(p.price)}</b>{p.compare_at_price&&Number(p.compare_at_price)>Number(p.price)&&<del>{money(p.compare_at_price)}</del>}<button onClick={()=>{setSelected(p);setSize(p.sizes?.[0]||'');setColor(p.colors?.[0]||'')}} aria-label={'Choose options for '+p.name}><Plus size={18}/></button></div></div></article>)}</div>
  {!loading&&!error&&!products.length&&<div className="empty"><ShoppingBag size={27}/><h3>No products here yet</h3><p>Try another category or clear your search to see all available styles.</p><button className="secondary" onClick={()=>{setCategory('all');setSearch('');setMobileActive('home')}}>Show all styles</button></div>}
 </>

 return <div className="site app-shell">
  <aside className="app-sidebar">
   <button className="brand app-brand" onClick={()=>{setCategory('all');setSearch('');setMobileActive('home')}}><img className="logo-image" src="/b-tech-logo.png" alt="B Tech logo" /><span><b>BALA FASHION</b><small>RAYACHOTY</small></span></button>
   <div className="sidebar-caption">YOUR STORE</div>
   <nav className="sidebar-nav" aria-label="App navigation">
    <button className={mobileActive==='home'?'active':''} onClick={()=>{setDrawer('');setMobileActive('home');setCategory('all');setSearch('')}}><Home size={19}/><span>Home</span></button>
    <button className={mobileActive==='categories'?'active':''} onClick={()=>{setDrawer('');setMobileActive('categories');setCategory('all')}}><Grid2X2 size={19}/><span>Categories</span></button>
    <button className={mobileActive==='shop'?'active':''} onClick={()=>{setDrawer('');setMobileActive('shop');setCategory('all')}}><Store size={19}/><span>Shop all</span></button>
    <button className={mobileActive==='bag'?'active':''} onClick={()=>{setMobileActive('bag');setDrawer('cart')}}><ShoppingBag size={19}/><span>My bag</span>{count>0&&<b className="sidebar-count">{count}</b>}</button>
    <button className={mobileActive==='account'?'active':''} onClick={()=>{setMobileActive('account');session?setDrawer('account'):login()}}><UserRound size={19}/><span>Account</span></button>
   </nav>
   <div className="sidebar-bottom"><span className="status-dot"/><span>Rayachoty store</span><small>Local fashion · COD</small></div>
  </aside>
  <div className="app-workspace">
   <header className="app-topbar">
    <div className="app-mobile-brand"><img className="logo-image" src="/b-tech-logo.png" alt="B Tech logo" /><span><b>BALA FASHION</b><small>RAYACHOTY</small></span></div>
    <div className="app-breadcrumb"><span>Store</span><ArrowRight size={14}/><b>{({home:'Overview',categories:'Categories',shop:'All products',search:'Search results',bag:'Your bag',account:'Account'})[mobileActive]||'Overview'}</b></div>
    <label className="app-search"><Search size={18}/><input ref={searchInputRef} aria-label="Search clothing" placeholder="Search products, styles..." value={search} onFocus={()=>{setDrawer('');setMobileActive('search')}} onChange={e=>{setDrawer('');setSearch(e.target.value);setMobileActive('search')}}/><kbd>⌕</kbd></label>
    <button className="app-account-button" onClick={()=>session?setDrawer('account'):login()}>{session?.user?.user_metadata?.avatar_url?<img src={session.user.user_metadata.avatar_url} alt="Profile"/>:<UserRound size={18}/>}<span>{session?.user?.user_metadata?.full_name?.split(' ')[0]||'Sign in'}</span></button>
    <button className="app-bag-button" aria-label={'Open bag, '+count+' items'} onClick={()=>{setMobileActive('bag');setDrawer('cart')}}><ShoppingBag size={19}/>{count>0&&<b>{count}</b>}</button>
   </header>
   <main className="app-main">
    {mobileActive==='home'&&<div className="app-page app-home-page">
     <section className="home-greeting"><div><div className="home-location"><span className="home-live-dot"/><span>RAYACHOTY · LOCAL FASHION</span></div><h1>{session?.user?.user_metadata?.full_name?.split(' ')[0]?('Hey, '+session.user.user_metadata.full_name.split(' ')[0]+' 👋'):'Hey there 👋'}<br/><em>Find your style.</em></h1><p>Everyday looks, closer to home.</p></div><button className="home-profile-shortcut" aria-label="Open account" onClick={()=>{setMobileActive('account');session?setDrawer('account'):login()}}>{session?.user?.user_metadata?.avatar_url?<img src={session.user.user_metadata.avatar_url} alt=""/>:<UserRound size={21}/>}</button></section>
     <label className="home-search-shortcut"><Search size={18}/><input aria-label="Search styles" placeholder="Search clothes, styles and more..." value={search} onFocus={()=>setMobileActive('search')} onChange={e=>{setSearch(e.target.value);setMobileActive('search')}}/><ArrowRight size={17}/></label>
     <button className="app-promo home-promo" onClick={()=>setMobileActive('categories')}><span className="app-promo-copy"><small>THE RAYACHOTY EDIT</small><b>Good looks.<br/>Good days.</b><span>Explore collections <ArrowRight size={15}/></span></span><span className="app-promo-image">{categories.find(c=>c.slug!=='all'&&c.image_url)?.image_url?<img src={categories.find(c=>c.slug!=='all'&&c.image_url).image_url} alt="Featured category"/>:<span className="home-promo-monogram">BF</span>}</span></button>
     <div className="home-quick-actions"><button onClick={()=>{setCategory('all');setMobileActive('shop')}}><span className="home-action-icon"><Store size={18}/></span><span><b>Shop all</b><small>Explore the collection</small></span><ArrowRight size={16}/></button><button onClick={getOrders}><span className="home-action-icon"><Truck size={18}/></span><span><b>My orders</b><small>View your purchases</small></span><ArrowRight size={16}/></button></div>
     <section className="app-section home-categories-section"><div className="app-section-head"><div><h2>Shop by category</h2><p>Find something that feels like you</p></div><button onClick={()=>setMobileActive('categories')}>See all <ArrowRight size={15}/></button></div>
      <div className="app-category-row">{categories.filter(c=>c.slug!=='all').map((c,i)=><button className="app-category-shortcut" key={c.slug} onClick={()=>{setCategory(c.slug);setMobileActive('shop')}}><span className={'app-category-thumb tone-'+(i%5)}>{c.image_url?<img src={c.image_url} alt=""/>:<span>{c.name.slice(0,1)}</span>}</span><b>{c.name}</b></button>)}</div>
     </section>
     <section className="app-section home-products-section"><div className="app-section-head"><div><h2>Explore styles</h2><p>Live products from local sellers</p></div><button onClick={()=>{setCategory('all');setMobileActive('shop')}}>View all <ArrowRight size={15}/></button></div>{catalogContent}</section>
    </div>}
    {mobileActive==='categories'&&<div className="app-page"><section className="page-intro"><div className="eyebrow muted">DISCOVER YOUR STYLE</div><h1>Categories</h1><p>Choose a collection to explore available products.</p></section><div className="app-category-grid">{categories.filter(c=>c.slug!=='all').map((c,i)=><button className="app-category-card" key={c.slug} onClick={()=>{setCategory(c.slug);setMobileActive('shop')}}><span className={'app-category-card-image tone-'+(i%5)}>{c.image_url?<img src={c.image_url} alt={c.name}/>:<span>{c.name.slice(0,1)}</span>}</span><span><b>{c.name}</b><small>Explore collection <ArrowRight size={14}/></small></span></button>)}</div></div>}
    {mobileActive==='shop'&&<div className="app-page"><section className="page-intro"><div className="eyebrow muted">THE COLLECTION</div><h1>{categories.find(c=>c.slug===category)?.name||'All products'}</h1><p>Live products currently available from local sellers.</p></section><div className="app-filter-row">{categories.map(c=><button className={category===c.slug?'active':''} key={c.slug} onClick={()=>setCategory(c.slug)}>{c.name}</button>)}</div>{catalogContent}</div>}
    {mobileActive==='search'&&<div className="app-page"><section className="page-intro"><div className="eyebrow muted">FIND YOUR FIT</div><h1>Search</h1><p>{search ? 'Results for “'+search+'”' : 'Search products by name, category or style.'}</p></section>{search&&<button className="clear-search" onClick={()=>setSearch('')}>Clear search <X size={14}/></button>}{catalogContent}</div>}
    {mobileActive==='bag'&&<div className="app-page"><section className="page-intro"><div className="eyebrow muted">READY WHEN YOU ARE</div><h1>Your bag</h1><p>Your selected styles stay here while you shop.</p></section><button className="primary" onClick={()=>setDrawer('cart')}>Open bag <ShoppingBag size={17}/>{count>0&&<span>({count})</span>}</button></div>}
    {mobileActive==='account'&&<div className="app-page"><section className="page-intro"><div className="eyebrow muted">YOUR PROFILE</div><h1>Account</h1><p>Manage your profile, orders and store tools.</p></section><div className="app-account-card"><div className="app-account-avatar"><UserRound size={24}/></div><div><b>{session?.user?.user_metadata?.full_name||session?.user?.email||'Welcome to Bala Fashion'}</b><small>{profile?.role||'Sign in to access your account'}</small></div></div><button className="primary" onClick={()=>session?setDrawer('account'):login()}>{session?'Open account':'Continue with Google'} <ArrowRight size={16}/></button>{session&&<button className="secondary app-orders-button" onClick={getOrders}>View my orders</button>}</div>}
   </main>
   <nav className="mobile-bottom-nav" aria-label="Primary app navigation">
    <button className={`mobile-nav-item${mobileActive==='home'?' active':''}`} onClick={()=>{setDrawer('');setMobileActive('home');setCategory('all');setSearch('')}}><Home size={20}/><span>Home</span></button>
    <button className={`mobile-nav-item${mobileActive==='categories'?' active':''}`} onClick={()=>{setDrawer('');setMobileActive('categories');setSearch('')}}><Grid2X2 size={20}/><span>Categories</span></button>
    <button className={`mobile-nav-item${mobileActive==='search'?' active':''}`} onClick={()=>{setDrawer('');setMobileActive('search');setSearch('');searchInputRef.current?.focus()}}><Search size={20}/><span>Search</span></button>
    <button className={`mobile-nav-item${mobileActive==='bag'?' active':''}`} onClick={()=>{setDrawer('');setMobileActive('bag')}}><span className="mobile-bag-icon"><ShoppingBag size={20}/>{count>0&&<b>{count>99?'99+':count}</b>}</span><span>Bag</span></button>
    <button className={`mobile-nav-item${mobileActive==='account'?' active':''}`} onClick={()=>{setMobileActive('account');session?setDrawer('account'):login()}}><UserRound size={20}/><span>Account</span></button>
   </nav>
  </div>
  {drawer&&<div className="overlay" onMouseDown={e=>e.target===e.currentTarget&&setDrawer('')}><aside className="drawer"><div className="drawer-head"><div><div className="eyebrow muted">{drawer==='cart'?'YOUR SELECTION':drawer==='checkout'?'DELIVERY DETAILS':drawer==='orders'?'YOUR ACCOUNT':'BALA FASHION'}</div><h2>{({cart:'Your bag',checkout:'Checkout',orders:'My orders',account:'Account','categories-manage':'Manage category images'})[drawer]||'Manage products'}</h2></div><button className="icon" onClick={()=>setDrawer('')}><X/></button></div>
   {drawer==='cart'&&<div className="drawer-body">{!cart.length?<div className="empty"><ShoppingBag/><h3>Your bag is taking a break.</h3><p>Find a piece you love and add it here.</p><button className="primary" onClick={()=>setDrawer('')}>Keep exploring</button></div>:<>{cart.map(i=><div className="cart-item" key={i.key}><img src={i.image_url} alt={i.name}/><div><b>{i.name}</b><small>{i.size} {i.color&&`· ${i.color}`}</small><strong>{money(i.price)}</strong><div className="qty"><button onClick={()=>setCart(c=>c.map(x=>x.key===i.key?{...x,quantity:Math.max(1,x.quantity-1)}:x))}><Minus size={13}/></button>{i.quantity}<button onClick={()=>setCart(c=>c.map(x=>x.key===i.key?{...x,quantity:Math.min(Number(x.stock_quantity||20),x.quantity+1)}:x))}><Plus size={13}/></button><button className="remove" onClick={()=>setCart(c=>c.filter(x=>x.key!==i.key))}>Remove</button></div></div></div>)}{vendors.length>1&&<div className="warning">Please check out one seller at a time.</div>}<div className="summary"><div><span>Subtotal</span><b>{money(subtotal)}</b></div><small>Cash on delivery · Rayachoty service area</small><button className="primary full" disabled={vendors.length>1} onClick={()=>session?setDrawer('checkout'):login()}>Continue to checkout <ArrowRight size={16}/></button></div></>}</div>}
   {drawer==='checkout'&&<form className="drawer-body form" onSubmit={place}><p>Where should we deliver your order?</p>{[['recipient_name','Recipient name'],['phone','Mobile number'],['line1','House / street address'],['line2','Address line 2 (optional)'],['landmark','Landmark'],['city','City'],['postal_code','PIN code']].map(([key,label])=><label key={key}>{label}<input required={!['line2','landmark','postal_code'].includes(key)} value={address[key]} onChange={e=>setAddress({...address,[key]:e.target.value})}/></label>)}<label>Delivery notes<textarea rows="2" value={address.notes} onChange={e=>setAddress({...address,notes:e.target.value})}/></label><div className="cod"><Check size={17}/><span><b>Cash on delivery</b><small>Pay in cash when your order arrives.</small></span></div><div className="summary"><div><span>Total</span><b>{money(subtotal)}</b></div><button className="primary full" disabled={busy}>{busy?'Placing order…':'Place COD order'} <ArrowRight size={16}/></button></div></form>}
   {drawer==='orders'&&<div className="drawer-body">{!session?<div className="empty"><p>Sign in to see your orders.</p><button className="primary" onClick={login}>Continue with Google</button></div>:!orders.length?<div className="empty"><h3>No orders yet</h3><button className="secondary" onClick={getOrders}>Refresh orders</button></div>:orders.map(o=><div className="order" key={o.id}><div><b>{o.order_number}</b><small>{o.status?.replaceAll('_',' ')}</small></div><p>{new Date(o.created_at).toLocaleDateString('en-IN')} · COD</p><strong>{money(o.total)}</strong></div>)}</div>}
   {drawer==='account'&&<div className="drawer-body"><p>{session?.user?.user_metadata?.full_name||session?.user?.email}</p><p className="muted">{profile?.role||'customer'}</p><button className="secondary full" onClick={getOrders}>View my orders</button>{['vendor','admin'].includes(profile?.role)&&<button className="primary full" onClick={()=>setDrawer('manage')}>Manage products</button>}{profile?.role==='admin'&&<button className="secondary full" onClick={()=>{setCategoryForm({category_id:'',image_url:''});setDrawer('categories-manage')}}>Manage category images</button>}<button className="text" onClick={logout}>Sign out</button></div>}
   {drawer==='categories-manage'&&<form className="drawer-body form" onSubmit={saveCategoryImage}>
    <p>Upload a category image to show it on the storefront. Only administrators can save these changes.</p>
    <label>Category<select required value={categoryForm.category_id} onChange={e=>{const selected=categories.find(c=>c.id===e.target.value);setCategoryForm({category_id:e.target.value,image_url:selected?.image_url||''})}}><option value="">Choose category</option>{categories.filter(c=>c.slug!=='all'&&c.id).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
    <label>Category image (Cloudinary)<input type="file" accept="image/*" onChange={e=>uploadCategoryImage(e.target.files?.[0])}/></label>
    {categoryForm.image_url&&<img className="upload-preview" src={categoryForm.image_url} alt="Category image preview"/>}
    <button className="primary full" disabled={busy||!categoryForm.category_id||!categoryForm.image_url}>{busy?'Saving…':'Save category image'}</button>
   </form>}
   {drawer==='manage'&&<form className="drawer-body form" onSubmit={saveProduct}><p>Add a product to your approved store.</p>
    <label>Product name<input required value={productForm.name} onChange={e=>setProductForm({...productForm,name:e.target.value})}/></label>
    <label>Description<textarea rows="3" value={productForm.description} onChange={e=>setProductForm({...productForm,description:e.target.value})}/></label>
    <label>Approved vendor ID<input required value={productForm.vendor_id} onChange={e=>setProductForm({...productForm,vendor_id:e.target.value})} placeholder="Vendor UUID"/></label>
    <label>Category<select required value={productForm.category_id} onChange={e=>setProductForm({...productForm,category_id:e.target.value})}><option value="">Choose category</option>{categories.filter(c=>c.slug!=='all').map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
    <div className="form-two"><label>Price (₹)<input required type="number" min="0" step="0.01" value={productForm.price} onChange={e=>setProductForm({...productForm,price:e.target.value})}/></label><label>Compare price<input type="number" min="0" step="0.01" value={productForm.compare_at_price} onChange={e=>setProductForm({...productForm,compare_at_price:e.target.value})}/></label></div>
    <label>Product image (Cloudinary)<input type="file" accept="image/*" onChange={e=>uploadImage(e.target.files?.[0])}/></label>{productForm.image_url&&<img className="upload-preview" src={productForm.image_url} alt="Uploaded product preview"/>}
    <label>Sizes (comma separated)<input value={productForm.sizes} onChange={e=>setProductForm({...productForm,sizes:e.target.value})}/></label><label>Colours (comma separated)<input value={productForm.colors} onChange={e=>setProductForm({...productForm,colors:e.target.value})}/></label>
    <label>Stock quantity<input required type="number" min="0" value={productForm.stock_quantity} onChange={e=>setProductForm({...productForm,stock_quantity:e.target.value})}/></label>
    <button className="primary full" disabled={busy}>{busy?'Saving…':'Save product'}</button></form>}
  </aside></div>}
  {selected&&<div className="modal-backdrop" onMouseDown={e=>e.target===e.currentTarget&&setSelected(null)}><section className="modal"><button className="icon close" onClick={()=>setSelected(null)}><X/></button><div className="modal-photo">{selected.image_url?<img src={selected.image_url} alt={selected.name} onError={e=>{e.currentTarget.style.display='none';e.currentTarget.parentElement.classList.add('image-failed')}}/>:<span className="placeholder">BF</span>}</div><div className="modal-info"><div className="eyebrow muted">{selected.category_name||'CURATED STYLE'}</div><h2>{selected.name}</h2><small>Sold by {selected.vendor_name||'a local seller'}</small><h3>{money(selected.price)} {selected.compare_at_price&&<del>{money(selected.compare_at_price)}</del>}</h3><p>{selected.description||'A thoughtfully selected piece for your wardrobe.'}</p>{selected.sizes?.length>0&&<div className="options"><b>Choose size</b><div>{selected.sizes.map(s=><button className={size===s?'selected':''} key={s} onClick={()=>setSize(s)}>{s}</button>)}</div></div>}{selected.colors?.length>0&&<div className="options"><b>Choose colour</b><div>{selected.colors.map(c=><button className={color===c?'selected':''} key={c} onClick={()=>setColor(c)}>{c}</button>)}</div></div>}<button className="primary full" disabled={busy||Number(selected.stock_quantity??selected.stock??0)<1} onClick={()=>add(selected,size,color)}><ShoppingBag size={16}/> {Number(selected.stock_quantity??selected.stock??0)<1?'Currently unavailable':`Add to bag — ${money(selected.price)}`}</button><small className="delivery"><Truck size={14}/> Local delivery · Cash on delivery</small></div></section></div>}
  {toast&&<div className="toast"><Check size={16}/>{toast}</div>}
 </div>
}
