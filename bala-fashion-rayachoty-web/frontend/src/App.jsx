import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'
import { ArrowRight, Bell, CalendarDays, Check, ChevronDown, ChevronLeft, Clock3, CreditCard, Eye, EyeOff, Grid2X2, Home, LayoutDashboard, MapPin, Menu, Minus, Package, Pencil, Phone, Plus, Search, ShoppingBag, Sparkles, Store, Trash2, Truck, UserRound, X } from 'lucide-react'
import { supabase } from './supabase'
import { api } from './api'

const defaultCats = [{id:'all',name:'All styles',slug:'all'},...['Women','Men','Kids','Ethnic Wear','Accessories'].map((name,i)=>({id:name.toLowerCase(),name,slug:['women','men','kids','ethnic-wear','accessories'][i]}))]
const money = n => `₹${Number(n||0).toLocaleString('en-IN',{maximumFractionDigits:2})}`
const MINIMUM_ORDER_AMOUNT = 250
const RAYACHOTY_MAP_CENTER = [14.05742, 78.74865]
const RAYACHOTY_DELIVERY_RADIUS_METERS = 5000

L.Icon.Default.mergeOptions({
 iconRetinaUrl: markerIcon2x,
 iconUrl: markerIcon,
 shadowUrl: markerShadow,
})

function LocationPicker({latitude,longitude,onChange,label}) {
 const mapNode=useRef(null), mapRef=useRef(null), markerRef=useRef(null)
 const latest=useRef({latitude,longitude,onChange})
 const [locationError,setLocationError]=useState('')
 latest.current={latitude,longitude,onChange}

 useEffect(()=>{
  let cancelled=false
  const addPoint=(lat,lng)=>{
   latest.current.onChange({latitude:Number(lat).toFixed(6),longitude:Number(lng).toFixed(6)})
   setLocationError('')
  }
  const init=()=>{
   if(cancelled||!mapNode.current||mapRef.current)return
   const current=latest.current
   const hasPoint=current.latitude!==''&&current.longitude!==''&&Number.isFinite(Number(current.latitude))&&Number.isFinite(Number(current.longitude))
   const center=hasPoint?[Number(current.latitude),Number(current.longitude)]:RAYACHOTY_MAP_CENTER
   const map=L.map(mapNode.current,{scrollWheelZoom:false}).setView(center,hasPoint?16:13)
   L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
    maxZoom:19,
    attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>'
   }).addTo(map)
   const coverageCircle=L.circle(RAYACHOTY_MAP_CENTER,{
    radius:RAYACHOTY_DELIVERY_RADIUS_METERS,
    color:'#7b1e3a',weight:2,opacity:0.95,
    fillColor:'#7b1e3a',fillOpacity:0.12,interactive:false
   }).addTo(map)
   map.fitBounds(coverageCircle.getBounds(),{padding:[18,18]})
   const setMarker=(lat,lng)=>{
    if(!markerRef.current){
     markerRef.current=L.marker([lat,lng],{draggable:true}).addTo(map)
     markerRef.current.on('dragend',event=>{const p=event.target.getLatLng();addPoint(p.lat,p.lng)})
    }else markerRef.current.setLatLng([lat,lng])
   }
   if(hasPoint)setMarker(center[0],center[1])
   map.on('click',event=>{setMarker(event.latlng.lat,event.latlng.lng);addPoint(event.latlng.lat,event.latlng.lng)})
   mapRef.current=map
   map.__setMarker=setMarker
   map.whenReady(()=>{if(!cancelled)map.invalidateSize()})
  }
  init()
  return ()=>{
   cancelled=true
   if(mapRef.current){mapRef.current.remove();mapRef.current=null;markerRef.current=null}
  }
 },[])

 useEffect(()=>{
  const map=mapRef.current
  if(!map)return
  const lat=Number(latitude),lng=Number(longitude)
  if(latitude!==''&&longitude!==''&&Number.isFinite(lat)&&Number.isFinite(lng)){
   map.__setMarker?.(lat,lng)
  }else if(markerRef.current){map.removeLayer(markerRef.current);markerRef.current=null}
 },[latitude,longitude])

 function useCurrentLocation(){
  if(!navigator.geolocation){setLocationError('Location is not supported by this browser. Tap the map to place a pin.');return}
  setLocationError('Finding your current location…')
  navigator.geolocation.getCurrentPosition(
   position=>{latest.current.onChange({latitude:position.coords.latitude.toFixed(6),longitude:position.coords.longitude.toFixed(6)});setLocationError('')},
   ()=>setLocationError('Could not get your location. Allow location access or tap the map to place a pin.'),
   {enableHighAccuracy:true,timeout:12000,maximumAge:30000}
  )
 }
 return <section className="location-picker">
  <div className="location-picker-head"><b>{label}</b><button type="button" className="secondary" onClick={useCurrentLocation}><MapPin size={15}/> Use my location</button></div>
  <p>5 km delivery coverage from Rayachoti Bus Stand. Tap inside the circle or drag the pin to select your address.</p>
  <div ref={mapNode} className="location-map" role="application" aria-label={label+' map'} />
  <div className="location-coordinates"><span>Latitude: {latitude||'Not selected'}</span><span>Longitude: {longitude||'Not selected'}</span></div>
  {locationError&&<small className="location-error">{locationError}</small>}
  <small>Maroon circle: 5 km from Rayachoti Bus Stand. Final eligibility is checked using road distance. Map data &copy; OpenStreetMap contributors.</small>
 </section>
}

export default function App() {
 const [session,setSession]=useState(null),[profile,setProfile]=useState(null),[authEmail,setAuthEmail]=useState(''),[authPassword,setAuthPassword]=useState(''),[authMode,setAuthMode]=useState('signin'),[authSubmitting,setAuthSubmitting]=useState(false);const sessionRef=useRef(null)
 const [products,setProducts]=useState([]),[categories,setCategories]=useState(defaultCats)
 const [loading,setLoading]=useState(true),[error,setError]=useState(''),[search,setSearch]=useState(''),[category,setCategory]=useState('all')
 const [cart,setCart]=useState([]),[selected,setSelected]=useState(null),[size,setSize]=useState(''),[color,setColor]=useState('')
 const [drawer,setDrawer]=useState(''),[menu,setMenu]=useState(false),[toast,setToast]=useState(''),[orders,setOrders]=useState([]),[selectedOrder,setSelectedOrder]=useState(null),[orderReturnDrawer,setOrderReturnDrawer]=useState('orders')
 const [notifications,setNotifications]=useState([]),[notificationOpen,setNotificationOpen]=useState(false)
 const [busy,setBusy]=useState(false),[mobileActive,setMobileActive]=useState('home'),searchInputRef=useRef(null),[address,setAddress]=useState({recipient_name:'',phone:'',line1:'',line2:'',landmark:'',city:'Rayachoty',state:'Andhra Pradesh',latitude:'',longitude:'',notes:''}),[deliveryQuote,setDeliveryQuote]=useState(null),[deliveryQuoteLoading,setDeliveryQuoteLoading]=useState(false),[deliveryQuoteError,setDeliveryQuoteError]=useState('')
 const [productForm,setProductForm]=useState({name:'',description:'',price:'',compare_at_price:'',category_id:'',vendor_id:'',image_url:'',image_public_id:'',sizes:'S,M,L,XL',colors:'Black,Blue',stock_quantity:'1'})
 const [categoryForm,setCategoryForm]=useState({category_id:'',name:'',image_url:'',sort_order:'0'})
 const [adminCategories,setAdminCategories]=useState([]),[adminVendors,setAdminVendors]=useState([])
 const [vendorForm,setVendorForm]=useState({id:'',owner_id:'',name:'',phone:'',address:'',description:'',latitude:'',longitude:'',status:'pending'})
 const [sellerDashboard,setSellerDashboard]=useState(null),[dashboardLoading,setDashboardLoading]=useState(false)
 useEffect(()=>{if(!supabase){sessionRef.current=null;setSession(null);return}let active=true,initialEventSeen=false;const applySession=nextSession=>{if(!active)return;const value=nextSession||null;sessionRef.current=value;setSession(value);if(!value)setProfile(null)};const restoreSession=async()=>{try{const {data,error}=await supabase.auth.getSession();if(!active)return;if(error){if(!initialEventSeen&&!sessionRef.current)applySession(null);return}if(data?.session)applySession(data.session);else if(!initialEventSeen&&!sessionRef.current)applySession(null)}catch{if(active&&!initialEventSeen&&!sessionRef.current)applySession(null)}};const {data:{subscription}}=supabase.auth.onAuthStateChange((event,nextSession)=>{if(!active)return;if(event==='INITIAL_SESSION'){initialEventSeen=true;if(nextSession||!sessionRef.current)applySession(nextSession);return}if(event==='PASSWORD_RECOVERY'){setAuthMode('reset');setDrawer('account')}if(event==='SIGNED_IN'){applySession(nextSession);setDrawer('');return}if(event==='SIGNED_OUT'){applySession(null);setDrawer('');return}if(nextSession)applySession(nextSession)});restoreSession();const onVisibility=()=>{if(document.visibilityState==='visible')restoreSession()};window.addEventListener('focus',restoreSession);document.addEventListener('visibilitychange',onVisibility);return()=>{active=false;subscription.unsubscribe();window.removeEventListener('focus',restoreSession);document.removeEventListener('visibilitychange',onVisibility)}},[])
 useEffect(()=>{const canonical='bala-fashion-rayachoty-omega.vercel.app';const isVercelPreview=location.hostname.endsWith('.vercel.app')&&location.hostname!==canonical;if(isVercelPreview){const callbackHash=location.hash;const callbackQuery=location.search;const isOAuthCallback=callbackHash.includes('access_token=')||callbackHash.includes('refresh_token=')||callbackQuery.includes('code=')||callbackQuery.includes('error=');if(!isOAuthCallback)location.replace(`https://${canonical}${location.pathname}${location.search}${location.hash}`)}},[])
 useEffect(()=>{
  const vendorId=cart[0]?.vendor_id
  const lat=address.latitude,lng=address.longitude
  if(drawer!=='checkout'||!session?.access_token||!vendorId||lat===''||lng===''){
   setDeliveryQuote(null);setDeliveryQuoteError('');setDeliveryQuoteLoading(false);return
  }
  let active=true
  setDeliveryQuote(null);setDeliveryQuoteError('');setDeliveryQuoteLoading(true)
  const timer=window.setTimeout(async()=>{
   try{
    const quote=await api('/delivery/quote/',{method:'POST',token:session.access_token,body:JSON.stringify({vendor_id:vendorId,latitude:Number(lat),longitude:Number(lng)})})
    if(active)setDeliveryQuote(quote)
   }catch(error){if(active)setDeliveryQuoteError(error.message||'Could not calculate the road delivery route.')}
   finally{if(active)setDeliveryQuoteLoading(false)}
  },450)
  return ()=>{active=false;window.clearTimeout(timer)}
 },[drawer,session?.access_token,address.latitude,address.longitude,cart[0]?.vendor_id])

 useEffect(()=>{if(!session){setProfile(null);return}let active=true;api('/profile/',{token:session.access_token}).then(data=>{if(active)setProfile(data)}).catch(()=>{if(active)setProfile(null)});return()=>{active=false}},[session])
 useEffect(()=>{
  if(!session?.user?.id){setNotifications([]);setNotificationOpen(false);return}
  let active=true
  const load=async()=>{
   try{
    const data=await api('/notifications/',{token:session.access_token})
    if(active)setNotifications((data.results||[]).map(item=>({
     id:String(item.id),eventType:item.event_type,title:item.title,body:item.body,
     createdAt:item.created_at,read:Boolean(item.read_at),orderId:String(item.order_id||''),url:'/orders'
    })))
   }catch(error){if(active)console.warn('Account notifications unavailable:',error.message)}
  }
  load()
  const interval=window.setInterval(load,30000)
  window.addEventListener('focus',load)
  return()=>{active=false;window.clearInterval(interval);window.removeEventListener('focus',load)}
 },[session?.user?.id,session?.access_token])
 useEffect(()=>{const controller=new AbortController();const timer=window.setTimeout(()=>load(controller.signal),180);return()=>{window.clearTimeout(timer);controller.abort()}},[category,search])
 async function load(signal){setLoading(true);try{const q=new URLSearchParams();if(category!=='all')q.set('category',category);if(search.trim())q.set('search',search.trim());const [p,c]=await Promise.all([api(`/products/?${q}`,{signal}),api('/categories/',{signal}).catch(e=>{if(e.name==='AbortError')throw e;return defaultCats.slice(1)})]);setProducts(Array.isArray(p.results)?p.results:Array.isArray(p)?p:[]);setCategories([defaultCats[0],...c]);setError('')}catch(e){if(e.name!=='AbortError'){setProducts([]);setError('We could not load the live catalog. Check your connection and try again.')}}finally{if(!signal?.aborted)setLoading(false)}}
 function notify(t){setToast(t);window.setTimeout(()=>setToast(''),2600)}
 const unreadNotificationCount=notifications.filter(item=>!item.read).length
 async function loadNotifications(){
  if(!session?.access_token)return
  try{
   const data=await api('/notifications/',{token:session.access_token})
   setNotifications((data.results||[]).map(item=>({
    id:String(item.id),eventType:item.event_type,title:item.title,body:item.body,
    createdAt:item.created_at,read:Boolean(item.read_at),url:'/orders'
   })))
  }catch(error){notify(error.message||'Could not load account notifications.')}
 }
 function openNotifications(){
  if(!session){setDrawer('account');notify('Sign in to view your notifications.');return}
  setNotificationOpen(value=>!value)
  loadNotifications()
 }
 async function markNotificationRead(id){
  if(!session?.access_token)return
  try{await api('/notifications/',{method:'PATCH',token:session.access_token,body:JSON.stringify({id})});await loadNotifications()}
  catch(error){notify(error.message||'Could not update notification.')}
 }
 async function openNotificationOrder(item){
  setNotificationOpen(false);setMobileActive('account');setDrawer('orders')
  try{
   if(!session?.access_token)throw new Error('Sign in to view order details.')
   let rows=[]
   if(['vendor','admin'].includes(profile?.role)){
    const data=await api('/seller/dashboard/',{token:session.access_token})
    rows=data.orders||[]
   }else{
    const data=await api('/orders/',{token:session.access_token})
    rows=data.results||data||[]
   }
   setOrders(rows)
   const order=rows.find(row=>String(row.id)===String(item.orderId))
   if(order){setSelectedOrder(order);setOrderReturnDrawer(['vendor','admin'].includes(profile?.role)?'seller-dashboard':'orders');setDrawer('order-details')}
   else{setDrawer('orders');notify('That order is not available in this account.')}
  }catch(error){setDrawer('orders');notify(error.message||'Could not open order details.')}
  finally{markNotificationRead(item.id)}
 }
 async function markAllNotificationsRead(){
  if(!session?.access_token)return
  try{await api('/notifications/',{method:'PATCH',token:session.access_token,body:JSON.stringify({mark_all_read:true})});await loadNotifications()}
  catch(error){notify(error.message||'Could not update notifications.')}
 }
 async function login(){if(!supabase)return notify('Sign-in is not configured on this deployment. Please contact support.');try{const canonicalOrigin='https://bala-fashion-rayachoty-omega.vercel.app';const {error}=await supabase.auth.signInWithOAuth({provider:'google',options:{redirectTo:`${canonicalOrigin}/`,queryParams:{prompt:'select_account'}}});if(error)throw error}catch(error){notify(error.message||'Google sign-in could not be started. Please try again.')}}
 async function submitEmailAuth(e){e.preventDefault();if(!supabase)return notify('Set Supabase frontend environment variables first.');setAuthSubmitting(true);try{if(authMode==='reset'){const {data,error}=await supabase.auth.updateUser({password:authPassword});if(error)throw error;setAuthPassword('');setAuthMode('signin');setDrawer('');notify('Password updated successfully. You are signed in.');return}if(authMode==='signup'){const {data,error}=await supabase.auth.signUp({email:authEmail.trim(),password:authPassword,options:{emailRedirectTo:'https://bala-fashion-rayachoty-omega.vercel.app'}});if(error)throw error;if(data.session){setSession(data.session);setDrawer('');notify('Account created and signed in.')}else notify('Account created. Check your email to confirm your address, then sign in.')}else{const {data,error}=await supabase.auth.signInWithPassword({email:authEmail.trim(),password:authPassword});if(error)throw error;if(!data?.session?.access_token)throw new Error('Sign-in returned no active session. Confirm your email address, then try again.');setSession(data.session);setDrawer('');notify('Signed in successfully.')}}catch(e){notify(e.message||'Authentication failed. Please try again.')}finally{setAuthSubmitting(false)}}
 async function sendPasswordReset(e){e.preventDefault();if(!supabase)return notify('Set Supabase frontend environment variables first.');if(!authEmail.trim())return notify('Enter your email address first.');setAuthSubmitting(true);try{const {error}=await supabase.auth.resetPasswordForEmail(authEmail.trim(),{redirectTo:'https://bala-fashion-rayachoty-omega.vercel.app'});if(error)throw error;notify('If an account exists for that email, a password reset link has been sent. Check your inbox and spam folder.');setAuthMode('signin')}catch(e){notify(e.message||'Could not send the reset email. Please try again.')}finally{setAuthSubmitting(false)}}
 async function logout(){await supabase?.auth.signOut();setDrawer('');notify('Signed out')}
 const count=cart.reduce((n,p)=>n+p.quantity,0),subtotal=cart.reduce((n,p)=>n+Number(p.price)*p.quantity,0)
 const vendors=[...new Set(cart.map(p=>p.vendor_id||p.vendor_name))]
 function add(p,s=p.sizes?.[0]||'',c=p.colors?.[0]||''){const stock=Number(p.stock_quantity??p.stock??0);if(!Number.isFinite(stock)||stock<1){notify('This item is currently unavailable.');return}const key=`${p.id}:${s}:${c}`;setCart(old=>old.some(i=>i.key===key)?old.map(i=>i.key===key?{...i,quantity:Math.min(i.quantity+1,stock)}:i):[...old,{...p,key,quantity:1,size:s,color:c}]);setSelected(null);setDrawer('cart');notify('Added to your bag')}
 async function getOrders(){if(!session)return login();try{const r=await api('/orders/',{token:session.access_token});setOrders(r.results||r);setSelectedOrder(null);setNotificationOpen(false);setDrawer('orders')}catch(e){notify(e.message)}}
 function openOrderDetails(order,returnTo='orders'){setSelectedOrder(order);setOrderReturnDrawer(returnTo);setNotificationOpen(false);setDrawer('order-details')}
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
 async function openCategoryManagement(){
  if(!session)return login()
  setDrawer('categories-manage');setCategoryForm({category_id:'',name:'',image_url:'',sort_order:'0'})
  try{const rows=await api('/categories/manage/',{token:session.access_token});setAdminCategories(Array.isArray(rows)?rows:rows.results||[])}
  catch(e){notify(e.message)}
 }
 async function saveCategoryImage(e){
  e.preventDefault();if(busy)return;if(!session)return login()
  if(!categoryForm.name.trim()&&!categoryForm.category_id)return notify('Enter a category name or choose a category to update.')
  if(categoryForm.image_url&&!categoryForm.image_url.startsWith('https://res.cloudinary.com/'))return notify('Upload a category image through Cloudinary first.')
  setBusy(true)
  try{
   const editing=Boolean(categoryForm.category_id)
   const payload=editing
    ? {id:categoryForm.category_id,name:categoryForm.name.trim(),image_url:categoryForm.image_url,sort_order:Number(categoryForm.sort_order||0)}
    : {name:categoryForm.name.trim(),image_url:categoryForm.image_url,sort_order:Number(categoryForm.sort_order||0)}
   await api('/categories/manage/',{method:editing?'PATCH':'POST',token:session.access_token,body:JSON.stringify(payload)})
   const rows=await api('/categories/manage/',{token:session.access_token});setAdminCategories(Array.isArray(rows)?rows:rows.results||[])
   await load();setCategoryForm({category_id:'',name:'',image_url:'',sort_order:'0'});notify(editing?'Category updated':'Category created')
  }catch(e){notify(e.message)}finally{setBusy(false)}
 }
 async function deactivateCategory(cat){
  if(!session)return login();setBusy(true)
  try{await api('/categories/manage/?id='+encodeURIComponent(cat.id),{method:'DELETE',token:session.access_token});const rows=await api('/categories/manage/',{token:session.access_token});setAdminCategories(Array.isArray(rows)?rows:rows.results||[]);await load();notify('Category deactivated')}
  catch(e){notify(e.message)}finally{setBusy(false)}
 }
 async function openVendorManagement(){
  if(!session)return login()
  setDrawer('vendors-manage')
  try{const data=await api('/vendors/manage/',{token:session.access_token});setAdminVendors(data.results||[])}
  catch(e){notify(e.message)}
 }
 async function createVendor(e){
  e.preventDefault();if(busy)return;if(!session)return login()
  const editing=Boolean(vendorForm.id)
  const ownerId=vendorForm.owner_id.trim()
  const uuidPattern=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
  if(!editing&&!uuidPattern.test(ownerId))return notify('Enter a valid Supabase Auth user UUID (not a Django ID or email).')
  if(!vendorForm.name.trim())return notify('Enter the vendor/store name.')
  if(vendorForm.latitude===''||vendorForm.longitude==='')return notify('Select the vendor location on the map or use the current location.')
  setBusy(true)
  try{
   const payload={...vendorForm,owner_id:ownerId,name:vendorForm.name.trim(),latitude:Number(vendorForm.latitude),longitude:Number(vendorForm.longitude)}
   await api('/vendors/manage/',{method:editing?'PATCH':'POST',token:session.access_token,body:JSON.stringify(payload)})
   const data=await api('/vendors/manage/',{token:session.access_token})
   setAdminVendors(data.results||[])
   setVendorForm({id:'',owner_id:'',name:'',phone:'',address:'',description:'',latitude:'',longitude:'',status:'pending'})
   await refreshSellerDashboard()
   notify(editing?'Vendor delivery location updated':'Vendor created with delivery location')
  }catch(e){notify(e.message)}finally{setBusy(false)}
 }
 async function updateVendorStatus(vendor,status){
  if(!session)return login();setBusy(true)
  try{await api('/vendors/manage/',{method:'PATCH',token:session.access_token,body:JSON.stringify({id:vendor.id,status})});setAdminVendors(old=>old.map(v=>v.id===vendor.id?{...v,status}:v));await refreshSellerDashboard();notify('Vendor status updated')}
  catch(e){notify(e.message)}finally{setBusy(false)}
 }
 async function updateOrderStatus(order,status){
  if(!session)return login()
  setBusy(true)
  try{
   await api('/orders/manage/',{method:'PATCH',token:session.access_token,body:JSON.stringify({id:order.id,status})})
   await refreshSellerDashboard()
   notify(`Order ${order.order_number} updated to ${status.replaceAll('_',' ')}`)
  }catch(e){notify(e.message)}finally{setBusy(false)}
 }
 async function deleteOrder(order){
  if(profile?.role!=='admin')return notify('Only administrators can delete orders.')
  if(!window.confirm(`Permanently delete order ${order.order_number}? This cannot be undone. Stock will be restored if the order was not delivered.`))return
  if(!session)return login()
  setBusy(true)
  try{
   await api('/orders/manage/',{method:'DELETE',token:session.access_token,body:JSON.stringify({id:order.id})})
   await refreshSellerDashboard()
   notify(`Order ${order.order_number} deleted`)
  }catch(e){notify(e.message||'Order could not be deleted.')}finally{setBusy(false)}
 }
 async function refreshSellerDashboard(){
  if(!session)return login()
  setDashboardLoading(true)
  try{const data=await api('/seller/dashboard/',{token:session.access_token});setSellerDashboard(data);return data}
  catch(e){notify(e.message);return null}finally{setDashboardLoading(false)}
 }
 async function openSellerDashboard(){
  if(!session)return login()
  setDrawer('seller-dashboard')
  const data=await refreshSellerDashboard()
  if(data?.role==='vendor'&&!data.stores?.length)notify('Your seller account has no approved store yet. Contact the administrator.')
 }
 async function openAccountEntry(){
  if(!session){setMobileActive('account');setDrawer('account');return}
  let currentProfile=profile
  if(!currentProfile){
   try{currentProfile=await api('/profile/',{token:session.access_token});setProfile(currentProfile)}
   catch(e){setDrawer('account');notify('Could not load your account role. Please retry.');return}
  }
  setMobileActive('account')
  if(['vendor','admin'].includes(currentProfile?.role))await openSellerDashboard()
  else setDrawer('account')
 }
 function startNewProduct(){
  const firstStore=sellerDashboard?.stores?.find(s=>s.status==='approved')
  setProductForm({name:'',description:'',price:'',compare_at_price:'',category_id:'',vendor_id:profile?.role==='admin'?'':(firstStore?.id||''),image_url:'',image_public_id:'',sizes:'S,M,L,XL',colors:'Black,Blue',stock_quantity:'1'})
  setDrawer('manage')
 }
 function startEditProduct(product){
  setProductForm({id:product.id,name:product.name||'',description:product.description||'',price:String(product.price??''),compare_at_price:product.compare_at_price==null?'':String(product.compare_at_price),category_id:product.category_id||'',vendor_id:product.vendor_id||'',image_url:product.image_url||'',image_public_id:product.image_public_id||'',sizes:(product.sizes||[]).join(','),colors:(product.colors||[]).join(','),stock_quantity:String(product.stock_quantity??0)})
  setDrawer('manage')
 }
 async function hideProduct(product){
  if(!session)return login()
  setBusy(true)
  try{await api('/products/manage/?id='+encodeURIComponent(product.id),{method:'DELETE',token:session.access_token});notify('Product unpublished');await refreshSellerDashboard();await load()}
  catch(e){notify(e.message)}finally{setBusy(false)}
 }
 async function publishProduct(product){
  if(!session)return login()
  setBusy(true)
  try{
   await api('/products/manage/',{method:'PATCH',token:session.access_token,body:JSON.stringify({id:product.id,is_active:true})})
   notify('Product published')
   await refreshSellerDashboard()
   await load()
  }catch(e){notify(e.message)}finally{setBusy(false)}
 }
 async function saveProduct(e){
  e.preventDefault();if(busy)return;if(!session)return login();setBusy(true)
  try{
   const payload={...productForm,price:Number(productForm.price),compare_at_price:productForm.compare_at_price?Number(productForm.compare_at_price):null,stock_quantity:Number(productForm.stock_quantity),sizes:productForm.sizes.split(',').map(x=>x.trim()).filter(Boolean),colors:productForm.colors.split(',').map(x=>x.trim()).filter(Boolean)}
   await api('/products/manage/',{method:productForm.id?'PATCH':'POST',token:session.access_token,body:JSON.stringify(payload)})
   setProductForm({name:'',description:'',price:'',compare_at_price:'',category_id:'',vendor_id:'',image_url:'',image_public_id:'',sizes:'S,M,L,XL',colors:'Black,Blue',stock_quantity:'1'})
   await load();await refreshSellerDashboard();setDrawer('seller-dashboard');notify(productForm.id?'Product updated':'Product created')
  }catch(e){notify(e.message)}finally{setBusy(false)}
 }
 async function place(e){
  e.preventDefault();if(busy)return
  if(subtotal<MINIMUM_ORDER_AMOUNT){notify(`Minimum order amount is ${money(MINIMUM_ORDER_AMOUNT)}. Add ${money(MINIMUM_ORDER_AMOUNT-subtotal)} more to continue.`);setDrawer('cart');return}
  if(address.latitude===''||address.longitude==='')return notify('Select your delivery location on the map or use your current location.')
  if(!deliveryQuote||deliveryQuote.vendor_id!==cart[0]?.vendor_id)return notify('Wait for a valid road-distance delivery quote before placing the order.')
  if(!session)return login()
  if(vendors.length>1)return notify('Checkout one seller at a time.')
  setBusy(true)
  try{
   const payload={...address,city:'Rayachoty',state:'Andhra Pradesh',latitude:Number(address.latitude),longitude:Number(address.longitude)}
   const r=await api('/orders/',{method:'POST',token:session.access_token,body:JSON.stringify({address:payload,notes:address.notes,items:cart.map(i=>({product_id:i.id,quantity:i.quantity,size:i.size,color:i.color}))})})
   setCart([]);setOrders(o=>[r,...o]);setDeliveryQuote(null);setDrawer('orders');notify(`Order ${r.order_number} placed`)
  }catch(err){notify(err.message)}finally{setBusy(false)}
 }
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
    <button className={mobileActive==='account'?'active':''} onClick={openAccountEntry}><UserRound size={19}/><span>Account</span></button>
   </nav>
   <div className="sidebar-bottom"><span className="status-dot"/><span>Rayachoty store</span><small>Local fashion · COD</small></div>
  </aside>
  <div className="app-workspace">
   <header className="app-topbar">
    <div className="app-mobile-brand"><img className="logo-image" src="/b-tech-logo.png" alt="B Tech logo" /><span><b>BALA FASHION</b><small>RAYACHOTY</small></span></div>
    <div className="app-breadcrumb"><span>Store</span><ArrowRight size={14}/><b>{({home:'Overview',categories:'Categories',shop:'All products',search:'Search results',bag:'Your bag',account:'Account'})[mobileActive]||'Overview'}</b></div>
    <label className="app-search"><Search size={18}/><input ref={searchInputRef} aria-label="Search clothing" placeholder="Search products, styles..." value={search} onFocus={()=>{setDrawer('');setMobileActive('search')}} onChange={e=>{setDrawer('');setSearch(e.target.value);setMobileActive('search')}}/><kbd>⌕</kbd></label>
    <div className="notification-area">
      <button className={'notification-bell'+(notificationOpen?' is-open':'')} type="button" onClick={openNotifications} aria-label={unreadNotificationCount?'Notifications, '+unreadNotificationCount+' unread':'Notifications'} aria-expanded={notificationOpen} title="Notifications">
       <Bell size={19}/>{unreadNotificationCount>0&&<span className="notification-count">{unreadNotificationCount>99?'99+':unreadNotificationCount}</span>}
      </button>
      {notificationOpen&&<section className="notification-popover" aria-label="Notifications">
       <div className="notification-popover-head"><div><b>Notifications</b><small>{unreadNotificationCount?unreadNotificationCount+' unread':'You’re all caught up'}</small></div><div className="notification-head-actions">{unreadNotificationCount>0&&<button type="button" onClick={markAllNotificationsRead}>Mark all read</button>}<button type="button" className="notification-close" aria-label="Close notifications" onClick={()=>setNotificationOpen(false)}><X size={16}/></button></div></div>
       {!notifications.length?<div className="notification-empty"><span className="notification-empty-icon"><Bell size={22}/></span><b>No notifications yet</b><p>Only order placed and delivered updates appear here.</p></div>:
        <div className="notification-list">{notifications.map(item=><button key={item.id} type="button" className={'notification-item'+(item.read?' read':'')} onClick={()=>openNotificationOrder(item)}><span className="notification-item-mark"><Bell size={15}/></span><span className="notification-item-copy"><b>{item.title}</b><small>{item.body}</small><time>{new Date(item.createdAt).toLocaleString('en-IN',{dateStyle:'medium',timeStyle:'short'})}</time></span>{!item.read&&<i className="notification-unread-dot"/>}</button>)}</div>}
      </section>}
     </div>
     <button className="app-account-button" onClick={openAccountEntry}>{session?.user?.user_metadata?.avatar_url?<img src={session.user.user_metadata.avatar_url} alt="Profile"/>:<UserRound size={18}/>}<span>{(session?.user?.user_metadata?.full_name||session?.user?.user_metadata?.name||session?.user?.email?.split('@')[0])?.split(' ')[0]||'Sign in'}</span></button>
   </header>
   <main className="app-main">
    {mobileActive==='home'&&<div className="app-page app-home-page">
     <section className="home-greeting"><div><div className="home-location"><span className="home-live-dot"/><span>RAYACHOTY · LOCAL FASHION</span></div><h1>{(session?.user?.user_metadata?.full_name||session?.user?.user_metadata?.name||session?.user?.email?.split('@')[0])?('Hey, '+(session.user.user_metadata.full_name||session.user.user_metadata.name||session.user.email.split('@')[0]).split(' ')[0]+' 👋'):'Hey there 👋'}<br/><em>Find your style.</em></h1><p>Everyday looks, closer to home.</p></div></section>
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
    {mobileActive==='account'&&<div className="app-page"><section className="page-intro"><div className="eyebrow muted">YOUR PROFILE</div><h1>Account</h1><p>Manage your profile, orders and store tools.</p></section><div className="app-account-card"><div className="app-account-avatar"><UserRound size={24}/></div><div><b>{session?.user?.user_metadata?.full_name||session?.user?.user_metadata?.name||session?.user?.email||'Welcome to Bala Fashion'}</b><small>{profile?.role||'Sign in to access your account'}</small></div></div><button className="primary" onClick={openAccountEntry}>{session?(['vendor','admin'].includes(profile?.role)?'Open management dashboard':'Open account'):'Continue with Google'} <ArrowRight size={16}/></button>{session&&<button className="secondary app-orders-button" onClick={getOrders}>View my orders</button>}</div>}
   </main>
   <nav className="mobile-bottom-nav" aria-label="Primary app navigation">
    <button className={`mobile-nav-item${mobileActive==='home'?' active':''}`} onClick={()=>{setDrawer('');setMobileActive('home');setCategory('all');setSearch('')}}><Home size={20}/><span>Home</span></button>
    <button className={`mobile-nav-item${mobileActive==='categories'?' active':''}`} onClick={()=>{setDrawer('');setMobileActive('categories');setSearch('')}}><Grid2X2 size={20}/><span>Categories</span></button>
    <button className={`mobile-nav-item${mobileActive==='search'?' active':''}`} onClick={()=>{setDrawer('');setMobileActive('search');setSearch('');searchInputRef.current?.focus()}}><Search size={20}/><span>Search</span></button>
    <button className={`mobile-nav-item${drawer==='cart'?' active':''}`} onClick={()=>setDrawer('cart')}><span className="mobile-bag-icon"><ShoppingBag size={20}/>{count>0&&<b>{count>99?'99+':count}</b>}</span><span>Bag</span></button>
    <button className={`mobile-nav-item${drawer==='account'?' active':''}`} onClick={openAccountEntry}><UserRound size={20}/><span>Account</span></button>
   </nav>
  </div>
  {drawer&&<div className="overlay" onMouseDown={e=>e.target===e.currentTarget&&setDrawer('')}><aside className="drawer"><div className="drawer-head"><div><div className="eyebrow muted">{drawer==='cart'?'YOUR SELECTION':drawer==='checkout'?'DELIVERY DETAILS':drawer==='orders'||drawer==='order-details'?'YOUR ACCOUNT':'BALA FASHION'}</div><h2>{({cart:'Your bag',checkout:'Checkout',orders:'My orders','order-details':'Order details',account:'Account','categories-manage':'Manage categories','vendors-manage':'Manage vendors'})[drawer]||'Manage products'}</h2></div><button className="icon" onClick={()=>setDrawer('')}><X/></button></div>
   {drawer==='cart'&&<div className="drawer-body">{!cart.length?<div className="empty"><ShoppingBag/><h3>Your bag is taking a break.</h3><p>Find a piece you love and add it here.</p><button className="primary" onClick={()=>setDrawer('')}>Keep exploring</button></div>:<>{cart.map(i=><div className="cart-item" key={i.key}><img src={i.image_url} alt={i.name}/><div><b>{i.name}</b><small>{i.size} {i.color&&`· ${i.color}`}</small><strong>{money(i.price)}</strong><div className="qty"><button onClick={()=>setCart(c=>c.map(x=>x.key===i.key?{...x,quantity:Math.max(1,x.quantity-1)}:x))}><Minus size={13}/></button>{i.quantity}<button onClick={()=>setCart(c=>c.map(x=>x.key===i.key?{...x,quantity:Math.min(Number(x.stock_quantity||20),x.quantity+1)}:x))}><Plus size={13}/></button><button className="remove" onClick={()=>setCart(c=>c.filter(x=>x.key!==i.key))}>Remove</button></div></div></div>)}{vendors.length>1&&<div className="warning">Please check out one seller at a time.</div>}{subtotal<MINIMUM_ORDER_AMOUNT&&<div className="warning">Minimum order amount is {money(MINIMUM_ORDER_AMOUNT)}. Add {money(MINIMUM_ORDER_AMOUNT-subtotal)} more to continue.</div>}<div className="summary"><div><span>Subtotal</span><b>{money(subtotal)}</b></div><small>Cash on delivery · Rayachoty service area</small><button className="primary full" disabled={vendors.length>1||subtotal<MINIMUM_ORDER_AMOUNT} onClick={()=>session?setDrawer('checkout'):setDrawer('account')}>Continue to checkout <ArrowRight size={16}/></button></div></>}</div>}
   {drawer==='checkout'&&<form className="drawer-body form" onSubmit={place}>
    <p>Delivery is available only in Rayachoty. The final distance and fee are calculated on the server using the road route from this store.</p>
    { [['recipient_name','Recipient name'],['phone','Mobile number'],['line1','House / street address'],['line2','Address line 2 (optional)'],['landmark','Landmark']].map(([key,label])=><label key={key}>{label}<input required={!['line2','landmark'].includes(key)} value={address[key]} onChange={e=>setAddress({...address,[key]:e.target.value})}/></label>)}
    <div className="local-service-note"><MapPin size={16}/> Rayachoty, Andhra Pradesh · Maximum 5 km road distance from Rayachoti Bus Stand</div>
    <LocationPicker label="Your delivery location" latitude={address.latitude} longitude={address.longitude} onChange={({latitude,longitude})=>setAddress(p=>({...p,latitude,longitude}))}/>
    <div className="delivery-fee-preview">
     {deliveryQuoteLoading?<span>Calculating road route and delivery charge…</span>:deliveryQuoteError?<span className="location-error">{deliveryQuoteError}</span>:deliveryQuote?<><div><span>Road distance · {deliveryQuote.distance_km} km</span><b>{money(deliveryQuote.delivery_fee)}</b></div><small>₹5 per started 500 metres · maximum 5 km road distance · OpenStreetMap-compatible routing</small></>:<span>Select a map location to calculate the delivery charge.</span>}
    </div>
    <label>Delivery notes<textarea rows="2" value={address.notes} onChange={e=>setAddress({...address,notes:e.target.value})}/></label>
    <div className="cod"><Check size={17}/><span><b>Cash on delivery</b><small>Pay in cash when your order arrives.</small></span></div>
    <div className="summary">
     {subtotal<MINIMUM_ORDER_AMOUNT&&<div className="warning">Minimum order amount is {money(MINIMUM_ORDER_AMOUNT)}. Add {money(MINIMUM_ORDER_AMOUNT-subtotal)} more to place your order.</div>}
     <div><span>Items subtotal</span><b>{money(subtotal)}</b></div>
     <div><span>Delivery charge</span><b>{deliveryQuote?money(deliveryQuote.delivery_fee):'Calculate route first'}</b></div>
     <div><span>Total</span><b>{deliveryQuote?money(subtotal+Number(deliveryQuote.delivery_fee)):'—'}</b></div>
     <button className="primary full" disabled={busy||subtotal<MINIMUM_ORDER_AMOUNT||!deliveryQuote||deliveryQuoteLoading}>{busy?'Placing order…':'Place COD order'} <ArrowRight size={16}/></button>
    </div>
   </form>}
   {drawer==='orders'&&<div className="drawer-body account-orders-panel">{!session?<div className="empty"><p>Sign in to see your orders.</p><button className="primary" onClick={()=>setDrawer('account')}>Sign in to continue</button></div>:!orders.length?<div className="empty"><Package size={28}/><h3>No orders yet</h3><p>Your orders will appear here after checkout.</p><button className="secondary" onClick={getOrders}>Refresh orders</button></div>:<><div className="orders-intro"><span className="orders-intro-icon"><Package size={20}/></span><div><b>Your order history</b><small>{orders.length} order{orders.length===1?'':'s'} · Latest first</small></div><button className="secondary" onClick={getOrders}>Refresh</button></div>{orders.map(o=><button type="button" className="account-order-card" key={o.id} onClick={()=>openOrderDetails(o)}><span className="account-order-thumb">{o.items?.[0]?.image_url?<img src={o.items[0].image_url} alt=""/>:<Package size={21}/>}</span><span className="account-order-main"><b>{o.order_number}</b><small>{new Date(o.created_at).toLocaleDateString('en-IN',{dateStyle:'medium'})} · {o.items?.length||0} item line{(o.items?.length||0)===1?'':'s'}</small><span className={'order-status-chip status-'+String(o.status||'placed').replaceAll('_','-')}>{String(o.status||'placed').replaceAll('_',' ')}</span></span><span className="account-order-total"><b>{money(o.total)}</b><small>View details <ArrowRight size={12}/></small></span></button>)}</>}</div>}
   {drawer==='order-details'&&<div className="drawer-body order-detail-page">{!selectedOrder?<div className="empty"><p>Choose an order to view its details.</p><button className="secondary" onClick={getOrders}>Back to orders</button></div>:<><button className="order-back" onClick={()=>setDrawer(orderReturnDrawer)}><ChevronLeft size={17}/> Back</button><div className="order-detail-hero"><div className="order-detail-mark"><Package size={23}/></div><div><span className={'order-status-chip status-'+String(selectedOrder.status||'placed').replaceAll('_','-')}>{String(selectedOrder.status||'placed').replaceAll('_',' ')}</span><h3>{selectedOrder.order_number}</h3><p><CalendarDays size={14}/> Placed {new Date(selectedOrder.created_at).toLocaleString('en-IN',{dateStyle:'medium',timeStyle:'short'})}</p></div></div><section className="order-detail-section"><div className="order-detail-section-title"><h3>Items in this order</h3><span>{selectedOrder.items?.reduce((sum,item)=>sum+Number(item.quantity||0),0)||0} pieces</span></div>{(selectedOrder.items||[]).map((item,index)=><div className="order-detail-item" key={item.product_id||item.product_name+index}><div className="order-detail-image">{item.image_url?<img src={item.image_url} alt={item.product_name||'Product'} onError={e=>{e.currentTarget.style.display='none'}}/>:<Package size={19}/>}</div><div className="order-detail-item-copy"><b>{item.product_name||'Fashion item'}</b><small>{[item.size&&'Size '+item.size,item.color&&'Colour '+item.color].filter(Boolean).join(' · ')||'Standard option'}</small><small>Qty: {item.quantity} × {money(item.unit_price??(Number(item.line_total||0)/Math.max(1,Number(item.quantity||1))))}</small></div><strong>{money(item.line_total)}</strong></div>)}</section><section className="order-detail-section"><div className="order-detail-section-title"><h3><MapPin size={17}/> Delivery address</h3></div>{selectedOrder.address_snapshot&&typeof selectedOrder.address_snapshot==='object'?<div className="delivery-address-card"><b>{selectedOrder.address_snapshot.recipient_name||'Recipient'}</b><p>{[selectedOrder.address_snapshot.line1,selectedOrder.address_snapshot.line2,selectedOrder.address_snapshot.landmark].filter(Boolean).join(', ')}</p><p>{[selectedOrder.address_snapshot.city,selectedOrder.address_snapshot.state,selectedOrder.address_snapshot.postal_code].filter(Boolean).join(', ')}</p>{selectedOrder.address_snapshot.phone&&<span><Phone size={14}/> {selectedOrder.address_snapshot.phone}</span>}</div>:<p className="order-detail-muted">No saved address is available for this order.</p>}{selectedOrder.notes&&<p className="order-delivery-notes"><b>Delivery notes:</b> {selectedOrder.notes}</p>}</section><section className="order-detail-section"><div className="order-detail-section-title"><h3><CreditCard size={17}/> Payment & summary</h3></div><div className="order-payment-card"><div><span>Payment method</span><b>{String(selectedOrder.payment_method||'cod').toUpperCase()==='COD'?'Cash on delivery':String(selectedOrder.payment_method||'').toUpperCase()}</b></div><div><span>Payment status</span><b className={selectedOrder.payment_status==='paid'?'payment-success':'payment-pending'}>{selectedOrder.payment_status==='paid'?'Successful':String(selectedOrder.payment_status||'Pending').replaceAll('_',' ')}</b></div><div><span>Items subtotal</span><b>{money(selectedOrder.subtotal)}</b></div><div><span>Delivery fee</span><b>{money(selectedOrder.delivery_fee)}</b></div><div className="order-grand-total"><span>Total paid / due</span><b>{money(selectedOrder.total)}</b></div></div></section><section className="order-detail-section order-tracking-section"><div className="order-detail-section-title"><h3><Clock3 size={17}/> Order progress</h3></div><div className="order-progress">{['placed','confirmed','packed','out_for_delivery','delivered'].map((status,index)=>{const states=['placed','confirmed','packed','out_for_delivery','delivered'];const current=states.indexOf(selectedOrder.status);const done=current>=index;return <div className={'order-progress-step'+(done?' done':'')+(selectedOrder.status==='cancelled'?' cancelled':'')} key={status}><span className="order-progress-dot">{done?<Check size={12}/>:index+1}</span><div><b>{status.replaceAll('_',' ')}</b><small>{index===0?'Order received':index===1?'Seller confirmed':index===2?'Packed for dispatch':index===3?'On the way':'Delivered'}</small></div></div>})}{selectedOrder.status==='cancelled'&&<div className="order-cancelled-note">This order was cancelled.</div>}</div></section></>}</div>}
   {drawer==='account'&&(!session?<div className="drawer-body form auth-panel"><div className="auth-intro"><span className="auth-mark"><UserRound size={22}/></span><div className="eyebrow muted">BALA FASHION ACCOUNT</div><h3>{authMode==='forgot'?'Reset your password':authMode==='reset'?'Choose a new password':authMode==='signup'?'Create your account':'Welcome back'}</h3><p>{authMode==='forgot'?'We’ll email you a secure link to choose a new password.':authMode==='reset'?'Create a new password for your Bala Fashion account.':authMode==='signup'?'Join us to track orders and enjoy a smoother checkout.':'Sign in to track orders, save your details and shop your favourite styles.'}</p></div>{authMode!=='forgot'&&<><button className="primary full auth-google" type="button" onClick={login}><span className="google-g">G</span> Continue with Google <ArrowRight size={16}/></button><div className="auth-divider"><span>or continue with email</span></div></>}<form className="form auth-form" onSubmit={authMode==='forgot'?sendPasswordReset:submitEmailAuth}><label>Email address<input className="auth-input" type="email" autoComplete="email" required value={authEmail} onChange={e=>setAuthEmail(e.target.value)} placeholder="you@example.com"/></label>{authMode!=='forgot'&&<label>Password<input className="auth-input" type="password" autoComplete={authMode==='signup'||authMode==='reset'?'new-password':'current-password'} minLength={6} required value={authPassword} onChange={e=>setAuthPassword(e.target.value)} placeholder="At least 6 characters"/></label>}{authMode==='signin'&&<button className="text auth-forgot" type="button" onClick={()=>setAuthMode('forgot')}>Forgot password?</button>}<button className="primary full auth-submit" disabled={authSubmitting}>{authSubmitting?'Please wait…':authMode==='forgot'?'Send reset link':authMode==='reset'?'Update password':authMode==='signup'?'Create account':'Sign in with email'} <ArrowRight size={16}/></button>{authMode==='forgot'||authMode==='reset'?<button className="text full" type="button" onClick={()=>{setAuthMode('signin');setAuthPassword('')}}>Back to sign in</button>:<button className="text full auth-switch" type="button" onClick={()=>setAuthMode(m=>m==='signin'?'signup':'signin')}>{authMode==='signin'?"New to Bala Fashion? Create an account":'Already registered? Sign in'}</button>}</form><div className="auth-secure"><Check size={14}/> Secure sign-in powered by Supabase</div></div>:<div className="drawer-body"><p>{session?.user?.user_metadata?.full_name||session?.user?.user_metadata?.name||session?.user?.email}</p><p className="muted">{profile?.role||'customer'}</p><button className="secondary full" onClick={getOrders}>View my orders</button>{['vendor','admin'].includes(profile?.role)&&<button className="primary full" onClick={openSellerDashboard}><LayoutDashboard size={16}/> Seller dashboard</button>}{profile?.role==='admin'&&<button className="secondary full" onClick={openCategoryManagement}>Manage categories</button>}{profile?.role==='admin'&&<button className="secondary full" onClick={openVendorManagement}><Store size={16}/> Manage vendors</button>}<button className="text" onClick={logout}>Sign out</button></div>)}
   {drawer==='seller-dashboard'&&<div className="drawer-body seller-dashboard">
    <div className="seller-dashboard-head"><div><b>{profile?.role==='admin'?'Management dashboard':'Seller dashboard'}</b><small>{sellerDashboard?.stores?.length||0} store(s) available to your account</small></div><div className="seller-dashboard-head-actions"><button className="secondary" onClick={refreshSellerDashboard} disabled={dashboardLoading}>{dashboardLoading?'Refreshing…':'Refresh'}</button><button className="secondary" onClick={logout}>Sign out</button></div></div>
    {dashboardLoading&&!sellerDashboard?<p>Loading your dashboard…</p>:<>
     {profile?.role==='admin'&&<div className="seller-admin-actions"><button className="primary" onClick={openCategoryManagement}><Grid2X2 size={16}/> Manage categories</button><button className="secondary" onClick={openVendorManagement}><Store size={16}/> Manage vendors</button></div>}
     <div className="seller-stat-grid"><div><b>{sellerDashboard?.stats?.products??0}</b><small>Products</small></div><div><b>{sellerDashboard?.stats?.active_products??0}</b><small>Published</small></div><div><b>{sellerDashboard?.stats?.low_stock??0}</b><small>Low stock</small></div><div><b>{sellerDashboard?.stats?.orders??0}</b><small>Recent orders</small></div></div>
     {sellerDashboard?.stores?.length>0&&<section className="seller-dashboard-section"><h3>{profile?.role==='admin'?'Stores you can manage':'Your store'}</h3>{sellerDashboard.stores.map(store=><div className="seller-store-row" key={store.id}><span><b>{store.name}</b><small>{store.slug}</small></span><span className={'seller-status '+store.status}>{store.status}</span></div>)}</section>}
     <section className="seller-dashboard-section"><div className="seller-section-title"><h3>Product inventory</h3><button className="primary" onClick={startNewProduct} disabled={!sellerDashboard?.stores?.some(s=>s.status==='approved')}> <Plus size={15}/> Add product</button></div>
      {!sellerDashboard?.products?.length?<p className="seller-empty">No products in your managed stores yet.</p>:sellerDashboard.products.map(product=><article className="seller-product-row" key={product.id}><div className="seller-product-thumb">{product.image_url?<img src={product.image_url} alt={product.name}/>:<span>BF</span>}</div><div className="seller-product-main"><b>{product.name}</b><small>{product.vendor_name||'Store'} · {product.category_name||'Uncategorized'}</small><strong>{money(product.price)} · Stock {product.stock_quantity}</strong><span className={'seller-status '+(product.is_active?'approved':'suspended')}>{product.is_active?'Published':'Hidden'}</span></div><div className="seller-product-actions"><button className="secondary" aria-label={'Edit '+product.name} title="Edit product" onClick={()=>startEditProduct(product)}><Pencil size={15}/></button>{product.is_active?<button className="secondary" aria-label={'Unpublish '+product.name} title="Hide product from storefront" onClick={()=>hideProduct(product)} disabled={busy}><EyeOff size={15}/></button>:<button className="secondary" aria-label={'Publish '+product.name} title="Publish product to storefront" onClick={()=>publishProduct(product)} disabled={busy}><Eye size={15}/></button>}</div></article>)}
     </section>
     <section className="seller-dashboard-section"><h3>Order management</h3>{!sellerDashboard?.orders?.length?<p className="seller-empty">No orders yet.</p>:sellerDashboard.orders.slice(0,50).map(order=><article className="seller-order-row" key={order.id}><span><button type="button" className="order-detail-link" onClick={()=>openOrderDetails(order,'seller-dashboard')}>{order.order_number} <ArrowRight size={12}/></button><small>{order.vendor_name} · {new Date(order.created_at).toLocaleDateString('en-IN')}</small><small>{order.payment_method?.toUpperCase()||'COD'} · Payment: {order.payment_status==='paid'?'Successful':(order.payment_status||'Pending')}</small></span><span><b>{money(order.total)}</b><small>{String(order.status||'').replaceAll('_',' ')}</small><div className="seller-product-actions">{(({placed:['confirmed','cancelled'],confirmed:['packed','cancelled'],packed:['out_for_delivery'],out_for_delivery:['delivered']})[order.status]||[]).map(next=><button key={next} className="secondary" disabled={busy} onClick={()=>updateOrderStatus(order,next)}>{next.replaceAll('_',' ')}</button>)}{profile?.role==='admin'&&<button className="secondary" aria-label={`Delete order ${order.order_number}`} title="Permanently delete order" disabled={busy} onClick={()=>deleteOrder(order)}><Trash2 size={15}/><span>Delete</span></button>}</div></span></article>)}</section>
    </>}
   </div>}
   {drawer==='categories-manage'&&<div className="drawer-body form">
    <p>Create categories, edit their names and sort order, update category images, or deactivate categories. Existing product references are preserved.</p>
    <form className="form" onSubmit={saveCategoryImage}>
     <h3>{categoryForm.category_id?'Edit category':'Add category'}</h3>
     <label>Category name<input required value={categoryForm.name} onChange={e=>setCategoryForm(p=>({...p,name:e.target.value}))} placeholder="e.g. Western Wear"/></label>
     <label>Sort order<input type="number" step="1" value={categoryForm.sort_order} onChange={e=>setCategoryForm(p=>({...p,sort_order:e.target.value}))}/></label>
     <label>Category image (optional, Cloudinary)<input type="file" accept="image/*" onChange={e=>uploadCategoryImage(e.target.files?.[0])}/></label>
     {categoryForm.image_url&&<img className="upload-preview" src={categoryForm.image_url} alt="Category image preview"/>}
     <div className="form-two"><button className="primary full" disabled={busy||!categoryForm.name.trim()}>{busy?'Saving…':categoryForm.category_id?'Save category':'Create category'}</button><button type="button" className="secondary full" onClick={()=>setCategoryForm({category_id:'',name:'',image_url:'',sort_order:'0'})}>Clear</button></div>
    </form>
    <section className="seller-dashboard-section"><h3>All categories</h3>{!adminCategories.length?<p className="seller-empty">No categories found.</p>:adminCategories.map(cat=><article className="seller-store-row" key={cat.id}><span><b>{cat.name}</b><small>{cat.slug} · sort {cat.sort_order} · {cat.is_active?'Active':'Inactive'}</small></span><span className="seller-product-actions"><button className="secondary" onClick={()=>setCategoryForm({category_id:cat.id,name:cat.name,image_url:cat.image_url||'',sort_order:String(cat.sort_order??0)})}><Pencil size={15}/></button>{cat.is_active&&<button className="secondary" disabled={busy} onClick={()=>deactivateCategory(cat)}>Deactivate</button>}</span></article>)}</section>
   </div>}
   {drawer==='vendors-manage'&&<div className="drawer-body seller-dashboard">
    <div className="seller-section-title"><h3>Vendor management</h3><button className="secondary" onClick={openVendorManagement}>Refresh</button></div>
    <p>Create a store for an existing Supabase Auth user. The owner UUID is the Supabase Auth user ID, not a Django numeric ID. New vendor stores start pending unless you choose another status.</p>
    <form className="form admin-vendor-create" onSubmit={createVendor}>
     <h3>{vendorForm.id?'Update vendor delivery location':'Create vendor / store'}</h3>
     <label>Supabase Auth user UUID<input required value={vendorForm.owner_id} onChange={e=>setVendorForm(p=>({...p,owner_id:e.target.value.trimStart()}))} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" autoCapitalize="off" autoCorrect="off" spellCheck="false" readOnly={Boolean(vendorForm.id)}/></label>
     {!vendorForm.id&&<small>Find this UUID in Supabase → Authentication → Users → select the user → User ID. The user must already exist.</small>}
     <label>Vendor / store name<input required maxLength="180" value={vendorForm.name} onChange={e=>setVendorForm(p=>({...p,name:e.target.value}))} placeholder="e.g. Bala Fashion Store" readOnly={Boolean(vendorForm.id)}/></label>
     <label>Contact phone<input value={vendorForm.phone} onChange={e=>setVendorForm(p=>({...p,phone:e.target.value}))} placeholder="Mobile number" readOnly={Boolean(vendorForm.id)}/></label>
     <label>Store address<textarea rows="2" value={vendorForm.address} onChange={e=>setVendorForm(p=>({...p,address:e.target.value}))} placeholder="Store address"/></label>
     {!vendorForm.id&&<><label>Description<textarea rows="2" value={vendorForm.description} onChange={e=>setVendorForm(p=>({...p,description:e.target.value}))} placeholder="Optional store description"/></label>
     <label>Initial status<select value={vendorForm.status} onChange={e=>setVendorForm(p=>({...p,status:e.target.value}))}><option value="pending">Pending approval</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="suspended">Suspended</option></select></label></>}
     <LocationPicker label="Vendor store location" latitude={vendorForm.latitude} longitude={vendorForm.longitude} onChange={({latitude,longitude})=>setVendorForm(p=>({...p,latitude,longitude}))}/>
     <button className="primary full" disabled={busy}>{busy?'Saving…':vendorForm.id?'Save vendor location':'Create vendor with map location'}</button>
     {vendorForm.id&&<button type="button" className="secondary full" onClick={()=>setVendorForm({id:'',owner_id:'',name:'',phone:'',address:'',description:'',latitude:'',longitude:'',status:'pending'})}>Cancel location edit</button>}
    </form>
    {!adminVendors.length?<p className="seller-empty">No vendor records found.</p>:adminVendors.map(v=><article className="seller-store-row" key={v.id}><span><b>{v.name}</b><small>{v.owner_name||v.owner_id||'No owner'} · {v.phone||v.owner_phone||'No phone'}</small><small>{v.slug} · {v.latitude!=null&&v.longitude!=null?'Map pin set':'Map pin required'}</small></span><span className={'seller-status '+v.status}>{v.status}</span><div className="seller-vendor-actions"><button type="button" className="secondary" disabled={busy} onClick={()=>{setVendorForm({id:v.id,owner_id:v.owner_id||'',name:v.name||'',phone:v.phone||'',address:v.address||'',description:v.description||'',latitude:v.latitude==null?'':String(v.latitude),longitude:v.longitude==null?'':String(v.longitude),status:v.status||'pending'});document.querySelector('.admin-vendor-create')?.scrollIntoView({behavior:'smooth',block:'start'})}}>Set map pin</button>{['pending','approved','rejected','suspended'].map(st=><button key={st} className={v.status===st?'primary':'secondary'} disabled={busy||v.status===st} onClick={()=>updateVendorStatus(v,st)}>{st[0].toUpperCase()+st.slice(1)}</button>)}</div></article>)}
   </div>}
   {drawer==='manage'&&<form className="drawer-body form" onSubmit={saveProduct}><p>{productForm.id?'Update this product in your approved store.':'Add a product to your approved store.'}</p>
    <label>Product name<input required value={productForm.name} onChange={e=>setProductForm({...productForm,name:e.target.value})}/></label>
    <label>Description<textarea rows="3" value={productForm.description} onChange={e=>setProductForm({...productForm,description:e.target.value})}/></label>
    {profile?.role==='admin'?<label>Store<select required value={productForm.vendor_id} onChange={e=>setProductForm({...productForm,vendor_id:e.target.value})}><option value="">Choose approved store</option>{(sellerDashboard?.stores||[]).filter(s=>s.status==='approved').map(store=><option key={store.id} value={store.id}>{store.name}</option>)}</select></label>:<div className="seller-store-note">Store: <b>{sellerDashboard?.stores?.find(s=>s.id===productForm.vendor_id)?.name||sellerDashboard?.stores?.[0]?.name||'Your approved store'}</b><small>The server assigns products to your own approved store.</small></div>}
    <label>Category<select required value={productForm.category_id} onChange={e=>setProductForm({...productForm,category_id:e.target.value})}><option value="">Choose category</option>{categories.filter(c=>c.slug!=='all').map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
    <div className="form-two"><label>Price (₹)<input required type="number" min="0" step="0.01" value={productForm.price} onChange={e=>setProductForm({...productForm,price:e.target.value})}/></label><label>Compare price<input type="number" min="0" step="0.01" value={productForm.compare_at_price} onChange={e=>setProductForm({...productForm,compare_at_price:e.target.value})}/></label></div>
    <label>Product image (Cloudinary)<input type="file" accept="image/*" onChange={e=>uploadImage(e.target.files?.[0])}/></label>{productForm.image_url&&<img className="upload-preview" src={productForm.image_url} alt="Uploaded product preview"/>}
    <label>Sizes (comma separated)<input value={productForm.sizes} onChange={e=>setProductForm({...productForm,sizes:e.target.value})}/></label><label>Colours (comma separated)<input value={productForm.colors} onChange={e=>setProductForm({...productForm,colors:e.target.value})}/></label>
    <label>Stock quantity<input required type="number" min="0" value={productForm.stock_quantity} onChange={e=>setProductForm({...productForm,stock_quantity:e.target.value})}/></label>
    <button className="primary full" disabled={busy}>{busy?'Saving…':(productForm.id?'Update product':'Save product')}</button><button type="button" className="secondary full" onClick={()=>setDrawer('seller-dashboard')}>Cancel</button></form>}
  </aside></div>}
  {selected&&<div className="modal-backdrop" onMouseDown={e=>e.target===e.currentTarget&&setSelected(null)}><section className="modal"><button className="icon close" onClick={()=>setSelected(null)}><X/></button><div className="modal-photo">{selected.image_url?<img src={selected.image_url} alt={selected.name} onError={e=>{e.currentTarget.style.display='none';e.currentTarget.parentElement.classList.add('image-failed')}}/>:<span className="placeholder">BF</span>}</div><div className="modal-info"><div className="eyebrow muted">{selected.category_name||'CURATED STYLE'}</div><h2>{selected.name}</h2><small>Sold by {selected.vendor_name||'a local seller'}</small><h3>{money(selected.price)} {selected.compare_at_price&&<del>{money(selected.compare_at_price)}</del>}</h3><p>{selected.description||'A thoughtfully selected piece for your wardrobe.'}</p>{selected.sizes?.length>0&&<div className="options"><b>Choose size</b><div>{selected.sizes.map(s=><button className={size===s?'selected':''} key={s} onClick={()=>setSize(s)}>{s}</button>)}</div></div>}{selected.colors?.length>0&&<div className="options"><b>Choose colour</b><div>{selected.colors.map(c=><button className={color===c?'selected':''} key={c} onClick={()=>setColor(c)}>{c}</button>)}</div></div>}<button className="primary full" disabled={busy||Number(selected.stock_quantity??selected.stock??0)<1} onClick={()=>add(selected,size,color)}><ShoppingBag size={16}/> {Number(selected.stock_quantity??selected.stock??0)<1?'Currently unavailable':`Add to bag — ${money(selected.price)}`}</button><small className="delivery"><Truck size={14}/> Local delivery · Cash on delivery</small></div></section></div>}
  {toast&&<div className="toast"><Check size={16}/>{toast}</div>}
 </div>
}
