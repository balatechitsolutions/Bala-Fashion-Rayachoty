import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'
import { FaHouse, FaLayerGroup, FaBagShopping, FaCircleUser } from 'react-icons/fa6'
import { FiArrowRight, FiBell, FiCalendar, FiCheck, FiChevronDown, FiChevronLeft, FiClock, FiCreditCard, FiDownload, FiEye, FiEyeOff, FiGrid, FiHome, FiLayout, FiMapPin, FiMenu, FiMinus, FiPackage, FiEdit2, FiPhone, FiPlus, FiSearch, FiShoppingBag, FiStar, FiTrash2, FiTruck, FiUser, FiVolume2, FiX } from 'react-icons/fi'
import { supabase } from './supabase'
import { DeliveryDashboard, DeliveryManagement } from './DeliveryDashboard'
import { AddressManagement } from './AddressManagement'
import { OrderAddressRepair } from './OrderAddressRepair'
import { api } from './api'
import { enableFirebaseNotifications, firebaseConfigured, subscribeToFirebaseMessages } from './firebase'

const defaultCats = [{id:'all',name:'All styles',slug:'all'},...['Women','Men','Kids','Ethnic Wear','Accessories'].map((name,i)=>({id:name.toLowerCase(),name,slug:['women','men','kids','ethnic-wear','accessories'][i]}))]
const money = n => `₹${Number(n||0).toLocaleString('en-IN',{maximumFractionDigits:2})}`
const deliveryAddressComplete = address => { const phone=String(address?.phone||''); const digits=phone.replace(/[^0-9]/g,'').length; const lat=Number(address?.latitude),lng=Number(address?.longitude); return Boolean(String(address?.recipient_name||'').trim()&&/^[0-9+() -]{10,16}$/.test(phone)&&digits>=10&&digits<=15&&String(address?.line1||'').trim()&&address?.latitude!=null&&address?.longitude!=null&&Number.isFinite(lat)&&Number.isFinite(lng)&&lat>=-90&&lat<=90&&lng>=-180&&lng<=180) }
const normalizeAddressSnapshot = value => { if (typeof value === 'string') { try { const parsed = JSON.parse(value); return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null } catch { return null } } return value && typeof value === 'object' && !Array.isArray(value) ? value : null }
const MINIMUM_ORDER_AMOUNT = 250
const RAYACHOTY_MAP_CENTER = [14.05742, 78.74865]
const DELIVERY_RADIUS_METERS = 5000

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
   const center=RAYACHOTY_MAP_CENTER
   const map=L.map(mapNode.current,{scrollWheelZoom:false}).setView(center,13)
   L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
    maxZoom:19,
    attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>'
   }).addTo(map)
   const coverageCircle=L.circle(center,{
    radius:DELIVERY_RADIUS_METERS,
    color:'#b42318',
    weight:2,
    opacity:0.95,
    fillColor:'#e5484d',
    fillOpacity:0.13
   }).addTo(map)
   coverageCircle.bindTooltip('Approx. 5 km delivery coverage from Rayachoti Bus Stand')
   map.fitBounds(coverageCircle.getBounds(),{padding:[18,18]})
   const setMarker=(lat,lng)=>{
    if(!markerRef.current){
     markerRef.current=L.marker([lat,lng],{draggable:true}).addTo(map)
     markerRef.current.on('dragend',event=>{const p=event.target.getLatLng();addPoint(p.lat,p.lng)})
    }else markerRef.current.setLatLng([lat,lng])
   }
   if(hasPoint)setMarker(Number(current.latitude),Number(current.longitude))
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
  <div className="location-picker-head"><b>{label}</b><button type="button" className="secondary" onClick={useCurrentLocation}><FiMapPin size={15}/> Use my location</button></div>
  <p>Tap the map or drag the pin to the exact location. Only Rayachoty local deliveries are supported.</p>
  <div ref={mapNode} className="location-map" role="application" aria-label={label+' map'} />
  <div className="location-coordinates"><span>Latitude: {latitude||'Not selected'}</span><span>Longitude: {longitude||'Not selected'}</span></div>
  {locationError&&<small className="location-error">{locationError}</small>}
  <small>Map data &copy; OpenStreetMap contributors.</small>
 </section>
}

function SearchableUserSelect({users,value,onChange,label,placeholder,excludeRoles=[]}) {
 const [query,setQuery]=useState('')
 const eligible=users.filter(user=>user.email&&!excludeRoles.includes(user.role)&&String(user.email).toLowerCase().includes(query.trim().toLowerCase()))
 return <div className="searchable-user-select">
  <label>Search {label.toLowerCase()} by email<input type="search" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Search registered email…" autoComplete="off"/></label>
  <label>{label} account<select required value={value} onChange={event=>onChange(event.target.value)}>
   <option value="">{placeholder||'Choose website user'}</option>
   {eligible.map(user=><option key={user.id} value={user.id}>{user.email}{user.full_name?' — '+user.full_name:''}</option>)}
  </select></label>
  {!eligible.length&&<small>No eligible users match this email search.</small>}
 </div>
}
export default function App() {
 const [session,setSession]=useState(null),[profile,setProfile]=useState(null),[authEmail,setAuthEmail]=useState(''),[authPassword,setAuthPassword]=useState(''),[authMode,setAuthMode]=useState('signin'),[authSubmitting,setAuthSubmitting]=useState(false);const sessionRef=useRef(null)
 const [products,setProducts]=useState([]),[categories,setCategories]=useState(defaultCats),[nextOffset,setNextOffset]=useState(null),[hasMore,setHasMore]=useState(false),[loadingMore,setLoadingMore]=useState(false)
 const [recommendationCatalog,setRecommendationCatalog]=useState([]),[recommendationLoading,setRecommendationLoading]=useState(false)
 const [interestSignals,setInterestSignals]=useState(()=>{try{const saved=window.localStorage.getItem('bala-fashion-interest-signals-v1');const parsed=saved?JSON.parse(saved):[];return Array.isArray(parsed)?parsed:[]}catch{return []}})
 const [loading,setLoading]=useState(true),[error,setError]=useState(''),[search,setSearch]=useState(''),[category,setCategory]=useState('all'),[categorySearch,setCategorySearch]=useState(''),[focusedMainCategory,setFocusedMainCategory]=useState(''),[categoriesLoading,setCategoriesLoading]=useState(true),[categoriesError,setCategoriesError]=useState('')
 const [cart,setCart]=useState([]),[selected,setSelected]=useState(null),[size,setSize]=useState(''),[color,setColor]=useState(''),[selectedImageIndex,setSelectedImageIndex]=useState(0),[detailLoading,setDetailLoading]=useState(false)
 const [drawer,setDrawer]=useState(''),[menu,setMenu]=useState(false),[toast,setToast]=useState(''),[orders,setOrders]=useState([]),[selectedOrder,setSelectedOrder]=useState(null),[orderReturnDrawer,setOrderReturnDrawer]=useState('orders')
 const [notifications,setNotifications]=useState([]),[notificationOpen,setNotificationOpen]=useState(false)
 const [installPrompt,setInstallPrompt]=useState(null),[pushEnabled,setPushEnabled]=useState(false),[soundEnabled,setSoundEnabled]=useState(false),[alertsBusy,setAlertsBusy]=useState(false)
 const seenNotificationIds=useRef(null)
 const selectedOrderAddress = normalizeAddressSnapshot(selectedOrder?.address_snapshot)
 const selectedImages = selected ? [
  ...(selected.image_url ? [{id:'primary',image_url:selected.image_url,alt_text:selected.name||'Product image'}] : []),
  ...(Array.isArray(selected.gallery_images)?selected.gallery_images:[])
 ] : []
 const selectedHeroImage = selectedImages[selectedImageIndex] || selectedImages[0] || null
 const [busy,setBusy]=useState(false),[mobileActive,setMobileActive]=useState('home'),[sellerOrderSearch,setSellerOrderSearch]=useState(''),[sellerProductSearch,setSellerProductSearch]=useState(''),searchInputRef=useRef(null),[addressReturnDrawer,setAddressReturnDrawer]=useState('account'),[address,setAddress]=useState({recipient_name:'',phone:'',line1:'',line2:'',landmark:'',city:'Rayachoty',state:'Andhra Pradesh',postal_code:'',latitude:'',longitude:'',notes:'',id:''}),[orderNotes,setOrderNotes]=useState(''),[deliveryQuote,setDeliveryQuote]=useState(null),[deliveryQuoteLoading,setDeliveryQuoteLoading]=useState(false),[deliveryQuoteError,setDeliveryQuoteError]=useState('')
 useEffect(()=>{
  window.scrollTo({top:0,left:0,behavior:'auto'})
  document.querySelector('.app-main')?.scrollTo({top:0,left:0,behavior:'auto'})
 },[mobileActive])
 const [productForm,setProductForm]=useState({name:'',description:'',additional_description:'',price:'',compare_at_price:'',category_id:'',vendor_id:'',image_url:'',image_public_id:'',extra_images:[],sizes:'S,M,L,XL',size_prices:'',colors:'Black,Blue',stock_quantity:'1'})
 const [categoryForm,setCategoryForm]=useState({category_id:'',name:'',parent_id:'',image_url:'',sort_order:'0'})
 const [adminCategories,setAdminCategories]=useState([]),[adminVendors,setAdminVendors]=useState([])
 const [authUsers,setAuthUsers]=useState([]),[authUsersLoading,setAuthUsersLoading]=useState(false),[authUsersFetched,setAuthUsersFetched]=useState(false)
 const [vendorForm,setVendorForm]=useState({id:'',owner_id:'',owner_email:'',owner_user_id:'',name:'',phone:'',address:'',description:'',latitude:'',longitude:'',status:'pending'})
 const [sellerDashboard,setSellerDashboard]=useState(null),[dashboardLoading,setDashboardLoading]=useState(false)
 useEffect(()=>{if(!supabase){sessionRef.current=null;setSession(null);return}let active=true,initialEventSeen=false;const applySession=nextSession=>{if(!active)return;const value=nextSession||null;sessionRef.current=value;setSession(value);if(!value)setProfile(null)};const restoreSession=async()=>{try{const {data,error}=await supabase.auth.getSession();if(!active)return;if(error){if(!initialEventSeen&&!sessionRef.current)applySession(null);return}if(data?.session)applySession(data.session);else if(!initialEventSeen&&!sessionRef.current)applySession(null)}catch{if(active&&!initialEventSeen&&!sessionRef.current)applySession(null)}};const {data:{subscription}}=supabase.auth.onAuthStateChange((event,nextSession)=>{if(!active)return;if(event==='INITIAL_SESSION'){initialEventSeen=true;if(nextSession||!sessionRef.current)applySession(nextSession);return}if(event==='PASSWORD_RECOVERY'){setAuthMode('reset');setDrawer('account')}if(event==='SIGNED_IN'){applySession(nextSession);setDrawer('');return}if(event==='SIGNED_OUT'){applySession(null);setAuthUsers([]);setAuthUsersFetched(false);setDrawer('');return}if(nextSession)applySession(nextSession)});restoreSession();const onVisibility=()=>{if(document.visibilityState==='visible')restoreSession()};window.addEventListener('focus',restoreSession);document.addEventListener('visibilitychange',onVisibility);return()=>{active=false;subscription.unsubscribe();window.removeEventListener('focus',restoreSession);document.removeEventListener('visibilitychange',onVisibility)}},[])
 useEffect(()=>{
  if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(error=>console.warn('PWA service worker registration failed:',error))
  const capture=event=>{event.preventDefault();setInstallPrompt(event)}
  window.addEventListener('beforeinstallprompt',capture)
  const installed=()=>setInstallPrompt(null)
  window.addEventListener('appinstalled',installed)
  return()=>{window.removeEventListener('beforeinstallprompt',capture);window.removeEventListener('appinstalled',installed)}
 },[])
 useEffect(()=>{const canonical='bala-fashion-rayachoty-omega.vercel.app';const isVercelPreview=location.hostname.endsWith('.vercel.app')&&location.hostname!==canonical;if(isVercelPreview){const callbackHash=location.hash;const callbackQuery=location.search;const isOAuthCallback=callbackHash.includes('access_token=')||callbackHash.includes('refresh_token=')||callbackQuery.includes('code=')||callbackQuery.includes('error=');if(!isOAuthCallback)location.replace(`https://${canonical}${location.pathname}${location.search}${location.hash}`)}},[])
 useEffect(()=>{
  if(drawer!=='checkout'||!session?.access_token)return
  let active=true
  api('/addresses/',{token:session.access_token}).then(data=>{
   const saved=(data.results||[]).find(item=>item.is_default)
   if(!active||!saved)return
   setAddress(current=>{
    if(current.id||current.recipient_name||current.phone||current.line1)return current
    return {...saved,latitude:String(saved.latitude??''),longitude:String(saved.longitude??'')}
   })
  }).catch(error=>{if(active)console.warn('Saved default delivery address could not be loaded:',error.message)})
  return ()=>{active=false}
 },[drawer,session?.access_token])

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
 useEffect(()=>{const controller=new AbortController();let active=true;setCategoriesLoading(true);api('/categories/',{signal:controller.signal}).then(rows=>{if(!active)return;if(!Array.isArray(rows))throw new Error('The category service returned an invalid response.');setCategories([defaultCats[0],...rows.filter(c=>c&&c.id&&c.slug&&c.is_active!==false)]);setCategoriesError('')}).catch(e=>{if(active&&e.name!=='AbortError'){setCategoriesError('Categories could not be loaded from the live catalog. Check the connection and retry.')}}).finally(()=>{if(active)setCategoriesLoading(false)});return()=>{active=false;controller.abort()}},[])
 function recordInterest(item,action='view'){
  if(!item)return
  const signal={productId:String(item.id||''),categorySlug:String(item.category_slug||item.slug||''),name:String(item.name||''),action,at:Date.now()}
  setInterestSignals(current=>{
   const next=[...current,signal].slice(-100)
   try{window.localStorage.setItem('bala-fashion-interest-signals-v1',JSON.stringify(next))}catch{}
   return next
  })
 }
 useEffect(()=>{
  if(mobileActive!=='home'||recommendationCatalog.length)return
  const controller=new AbortController()
  let active=true
  setRecommendationLoading(true)
  ;(async()=>{
   try{
    const all=[]
    let offset=0
    for(let page=0;page<3;page++){
     const result=await api('/products/?limit=60&offset='+offset,{signal:controller.signal})
     const rows=Array.isArray(result.results)?result.results:Array.isArray(result)?result:[]
     all.push(...rows)
     if(!result.has_more||result.next_offset==null||!rows.length)break
     offset=result.next_offset
    }
    if(active)setRecommendationCatalog(all)
   }catch(error){if(active&&error.name!=='AbortError')console.warn('Personalized product recommendations unavailable:',error.message)}
   finally{if(active)setRecommendationLoading(false)}
  })()
  return()=>{active=false;controller.abort()}
 },[mobileActive,recommendationCatalog.length])
 const recommendedProducts=(()=>{
  const weights={view:1,open:1.5,cart:4,category:2}
  const categoryScores=new Map()
  const productSeen=new Map()
  const now=Date.now()
  interestSignals.forEach(signal=>{
   const ageDays=Math.max(0,(now-Number(signal.at||now))/86400000)
   const recency=Math.exp(-ageDays/21)
   const weight=(weights[signal.action]||1)*recency
   if(signal.categorySlug)categoryScores.set(signal.categorySlug,(categoryScores.get(signal.categorySlug)||0)+weight)
   if(signal.productId)productSeen.set(signal.productId,(productSeen.get(signal.productId)||0)+weight)
  })
  return recommendationCatalog.filter(p=>Number(p.stock_quantity??p.stock??0)>0).map((p,index)=>{
   const categorySlug=String(p.category_slug||'')
   const interest=categoryScores.get(categorySlug)||0
   const seen=productSeen.get(String(p.id))||0
   const nameTokens=String(p.name||'').toLowerCase().split(/[^a-z0-9]+/).filter(t=>t.length>2)
   const likedTokens=new Set(interestSignals.filter(s=>s.action!=='category').flatMap(s=>String(s.name||'').toLowerCase().split(/[^a-z0-9]+/).filter(t=>t.length>2)))
   const textMatch=nameTokens.reduce((sum,token)=>sum+(likedTokens.has(token)?0.35:0),0)
   const freshness=Math.max(0,1-index/Math.max(recommendationCatalog.length,1))*0.15
   return {...p,__recommendationScore:interest+textMatch-seen*1.25+freshness}
  }).sort((a,b)=>b.__recommendationScore-a.__recommendationScore).slice(0,8)
 })()
 async function load(signal,offset=0,append=false){if(append)setLoadingMore(true);else setLoading(true);try{const q=new URLSearchParams();if(category!=='all')q.set('category',category);if(search.trim())q.set('search',search.trim());q.set('limit','30');q.set('offset',String(offset));const p=await api(`/products/?${q}`,{signal});const page=Array.isArray(p.results)?p.results:Array.isArray(p)?p:[];setProducts(current=>append?[...current,...page]:page);setHasMore(Boolean(p.has_more));setNextOffset(p.next_offset??null);setError('')}catch(e){if(e.name!=='AbortError'){if(!append)setProducts([]);setError('We could not load the live catalog. Check your connection and try again.')}}finally{if(!signal?.aborted){if(append)setLoadingMore(false);else setLoading(false)}}}
 function navigateMobilePage(page){
  setDrawer('')
  setMobileActive(page)
  if(page==='home'){setCategory('all');setSearch('')}
  else if(page==='categories'){setSearch('')}
  else if(page==='search'){setSearch('')}
  else if(page==='shop'){setCategory('all')}
  window.scrollTo({top:0,left:0,behavior:'auto'})
  document.querySelector('.app-main')?.scrollTo({top:0,left:0,behavior:'auto'})
 }
 function notify(t){setToast(t);window.setTimeout(()=>setToast(''),2600)}
 useEffect(()=>{
  if(!notifications.length)return
  const ids=notifications.map(item=>item.id)
  if(seenNotificationIds.current===null){seenNotificationIds.current=new Set(ids);return}
  const known=seenNotificationIds.current
  const fresh=notifications.filter(item=>!known.has(item.id))
  ids.forEach(id=>known.add(id))
  if(!fresh.length)return
  if(soundEnabled)playAlertSound()
  if('Notification' in window&&Notification.permission==='granted'&&document.visibilityState==='hidden'){
   fresh.forEach(item=>new Notification(item.title||'Bala Fashion update',{body:item.body||'You have a new order notification.',icon:'/b-tech-logo.png',tag:'bala-'+item.id}))
  }
 },[notifications,soundEnabled])
 function playAlertSound(){
  try{
   const AudioContextClass=window.AudioContext||window.webkitAudioContext
   if(!AudioContextClass)return
   const context=new AudioContextClass()
   const oscillator=context.createOscillator(),gain=context.createGain()
   oscillator.type='sine';oscillator.frequency.setValueAtTime(880,context.currentTime)
   oscillator.frequency.setValueAtTime(660,context.currentTime+0.12)
   gain.gain.setValueAtTime(0.0001,context.currentTime);gain.gain.exponentialRampToValueAtTime(0.16,context.currentTime+0.02)
   gain.gain.exponentialRampToValueAtTime(0.0001,context.currentTime+0.28)
   oscillator.connect(gain);gain.connect(context.destination);oscillator.start();oscillator.stop(context.currentTime+0.3)
   oscillator.onended=()=>context.close()
  }catch(error){console.warn('Notification sound unavailable:',error)}
 }
 async function enableAlertsAndSound(){
  if(!session?.access_token){setDrawer('account');notify('Sign in first to enable account notifications.');return}
  setAlertsBusy(true)
  try{
   if(!('Notification' in window))throw new Error('This browser does not support notifications.')
   const permission=Notification.permission==='granted'?'granted':await Notification.requestPermission()
   if(permission!=='granted')throw new Error('Allow notifications in your browser settings, then try again.')
   setSoundEnabled(true)
   playAlertSound()
   if('serviceWorker' in navigator)await navigator.serviceWorker.register('/sw.js')
   if(firebaseConfigured){
    const token=await enableFirebaseNotifications()
    await api('/notifications/devices/',{method:'POST',token:session.access_token,body:JSON.stringify({token})})
    setPushEnabled(true)
    const unsubscribe=await subscribeToFirebaseMessages(payload=>{
     playAlertSound()
     const title=payload?.notification?.title||payload?.data?.title||'Bala Fashion'
     const body=payload?.notification?.body||payload?.data?.body||'You have a new notification.'
     notify(title+': '+body)
    })
    window.__balaFirebaseMessageUnsubscribe?.()
    window.__balaFirebaseMessageUnsubscribe=unsubscribe
    notify('Browser push notifications and sound are enabled.')
   }else{
    setPushEnabled(false)
    notify('Browser alerts and sound enabled while the website is open. Configure Firebase web keys and Render service-account credentials for background push.')
   }
  }catch(error){notify(error.message||'Could not enable browser notifications.')}
  finally{setAlertsBusy(false)}
 }
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
 async function logout(){await supabase?.auth.signOut();setAuthUsers([]);setAuthUsersFetched(false);setDrawer('');notify('Signed out')}
 const count=cart.reduce((n,p)=>n+p.quantity,0),subtotal=cart.reduce((n,p)=>n+Number(p.price)*p.quantity,0)
 const vendors=[...new Set(cart.map(p=>p.vendor_id||p.vendor_name))]
 function priceForSize(product,chosenSize){const prices=product?.size_prices&&typeof product.size_prices==='object'?product.size_prices:{};const value=chosenSize&&prices[chosenSize]!=null?Number(prices[chosenSize]):Number(product?.price||0);return Number.isFinite(value)?value:Number(product?.price||0)}
 function add(p,s=p.sizes?.[0]||'',c=p.colors?.[0]||''){recordInterest(p,'cart');const stock=Number(p.stock_quantity??p.stock??0);if(!Number.isFinite(stock)||stock<1){notify('This item is currently unavailable.');return}const key=`${p.id}:${s}:${c}`;const unitPrice=priceForSize(p,s);setCart(old=>old.some(i=>i.key===key)?old.map(i=>i.key===key?{...i,quantity:Math.min(i.quantity+1,stock)}:i):[...old,{...p,key,price:unitPrice,quantity:1,size:s,color:c}]);setSelected(null);setDrawer('cart');notify('Added to your bag')}
 async function getOrders(){if(!session)return login();try{const r=await api('/orders/',{token:session.access_token});setOrders(r.results||r);setSelectedOrder(null);setNotificationOpen(false);setDrawer('orders')}catch(e){notify(e.message)}}
 function openOrderDetails(order,returnTo='orders'){setSelectedOrder(order);setOrderReturnDrawer(returnTo);setNotificationOpen(false);setDrawer('order-details')}
 async function openProductDetails(product){
  recordInterest(product,'view')
  setSelected(product);setSelectedImageIndex(0);setSize(product.sizes?.[0]||'');setColor(product.colors?.[0]||'');setDetailLoading(true)
  try{
   const details=await api('/products/'+encodeURIComponent(product.id)+'/')
   setSelected(current=>current&&String(current.id)===String(product.id)?{...current,...details}:current)
  }catch(error){notify(error.message||'Could not load full product details.')}
  finally{setDetailLoading(false)}
 }
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
 async function uploadGalleryImages(files){
  const selectedFiles=Array.from(files||[])
  if(!selectedFiles.length)return
  if(!session)return notify('Sign in with an approved vendor/admin account first.')
  if(productForm.extra_images.length+selectedFiles.length>8)return notify('Choose up to 8 additional product images.')
  if(selectedFiles.some(file=>!file.type.startsWith('image/')||file.size>8*1024*1024))return notify('Each gallery image must be an image smaller than 8 MB.')
  setBusy(true)
  try{
   const uploaded=[]
   for(const file of selectedFiles){
    const sign=await api('/uploads/signature/',{method:'POST',token:session.access_token,body:JSON.stringify({folder:'bala-fashion/products'})})
    const form=new FormData()
    Object.entries(sign.params).forEach(([key,value])=>form.append(key,value))
    form.append('api_key',sign.api_key);form.append('signature',sign.signature);form.append('file',file)
    const response=await fetch(`https://api.cloudinary.com/v1_1/${sign.cloud_name}/image/upload`,{method:'POST',body:form})
    const data=await response.json()
    if(!response.ok)throw new Error(data.error?.message||'Gallery image upload failed')
    uploaded.push({image_url:data.secure_url,image_public_id:data.public_id,alt_text:productForm.name||'Product image',sort_order:productForm.extra_images.length+uploaded.length})
   }
   setProductForm(p=>({...p,extra_images:[...p.extra_images,...uploaded]}))
   notify(`${uploaded.length} additional image(s) uploaded`)
  }catch(error){notify(error.message||'Could not upload gallery images.')}
  finally{setBusy(false)}
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
  setDrawer('categories-manage');setCategoryForm({category_id:'',name:'',parent_id:'',image_url:'',sort_order:'0'})
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
    ? {id:categoryForm.category_id,name:categoryForm.name.trim(),parent_id:categoryForm.parent_id||null,image_url:categoryForm.image_url,sort_order:Number(categoryForm.sort_order||0)}
    : {name:categoryForm.name.trim(),parent_id:categoryForm.parent_id||null,image_url:categoryForm.image_url,sort_order:Number(categoryForm.sort_order||0)}
   await api('/categories/manage/',{method:editing?'PATCH':'POST',token:session.access_token,body:JSON.stringify(payload)})
   const rows=await api('/categories/manage/',{token:session.access_token});setAdminCategories(Array.isArray(rows)?rows:rows.results||[])
   await load();setCategoryForm({category_id:'',name:'',parent_id:'',image_url:'',sort_order:'0'});notify(editing?'Category updated':'Category created')
  }catch(e){notify(e.message)}finally{setBusy(false)}
 }
 async function deactivateCategory(cat){
  if(!session)return login();setBusy(true)
  try{await api('/categories/manage/?id='+encodeURIComponent(cat.id),{method:'DELETE',token:session.access_token});const rows=await api('/categories/manage/',{token:session.access_token});setAdminCategories(Array.isArray(rows)?rows:rows.results||[]);await load();notify('Category deactivated')}
  catch(e){notify(e.message)}finally{setBusy(false)}
 }
 async function fetchAuthUsers(tokenOverride){
  const accessToken=tokenOverride||sessionRef.current?.access_token||session?.access_token
  if(!accessToken){notify('Your admin session is unavailable. Please sign in again, then reopen Delivery staff.');return}
  if(authUsersLoading)return
  setAuthUsersLoading(true)
  try{
   const data=await api('/users/manage/',{token:accessToken})
   setAuthUsers(Array.isArray(data.results)?data.results:[])
   setAuthUsersFetched(true)
   notify(`Fetched ${data.count??data.results?.length??0} website user(s).`)
  }catch(e){notify(e.message||'Could not fetch website users.')}
  finally{setAuthUsersLoading(false)}
 }
 async function openVendorManagement(){
  if(!session)return login()
  setDrawer('vendors-manage')
  if(!authUsersFetched)await fetchAuthUsers()
  try{const data=await api('/vendors/manage/',{token:session.access_token});setAdminVendors(data.results||[])}
  catch(e){notify(e.message)}
 }
 async function openDeliveryManagement(){
  // Read the live Supabase session before opening admin tools. A stale React
  // session state must not accidentally trigger Google OAuth and send the
  // administrator back to the storefront homepage.
  let activeSession=sessionRef.current||session
  if(!activeSession?.access_token&&supabase){
   try{
    const {data,error}=await supabase.auth.getSession()
    if(!error&&data?.session){
     activeSession=data.session
     sessionRef.current=activeSession
     setSession(activeSession)
    }
   }catch(error){notify(error.message||'Could not restore your admin session.');return}
  }
  if(!activeSession?.access_token){
   setMobileActive('account')
   setDrawer('account')
   notify('Your session has expired. Sign in again to manage delivery staff.')
   return
  }
  setDrawer('delivery-management')
  if(!authUsersFetched)await fetchAuthUsers(activeSession.access_token)
 }
 async function createVendor(e){
  e.preventDefault();if(busy)return;if(!session)return login()
  const editing=Boolean(vendorForm.id)
  const ownerUserId=vendorForm.owner_user_id.trim()
  if(!editing&&!ownerUserId)return notify('Search for and select an existing website user by email.')
  if(!vendorForm.name.trim())return notify('Enter the vendor/store name.')
  if(vendorForm.latitude===''||vendorForm.longitude==='')return notify('Select the vendor location on the map or use the current location.')
  setBusy(true)
  try{
   const payload={...vendorForm,owner_user_id:ownerUserId,name:vendorForm.name.trim(),latitude:Number(vendorForm.latitude),longitude:Number(vendorForm.longitude)}
   await api('/vendors/manage/',{method:editing?'PATCH':'POST',token:session.access_token,body:JSON.stringify(payload)})
   const data=await api('/vendors/manage/',{token:session.access_token})
   setAdminVendors(data.results||[])
   setVendorForm({id:'',owner_id:'',owner_email:'',owner_user_id:'',name:'',phone:'',address:'',description:'',latitude:'',longitude:'',status:'pending'})
   await refreshSellerDashboard()
   notify(editing?'Vendor delivery location updated':'Vendor created with delivery location')
  }catch(e){notify(e.message)}finally{setBusy(false)}
 }
 async function deleteVendor(vendor){
  if(profile?.role!=='admin')return notify('Only administrators can delete vendors.')
  if(!window.confirm('Permanently delete vendor '+vendor.name+'? Products will also be deleted. Vendors with order history cannot be deleted.'))return
  setBusy(true)
  try{
   await api('/vendors/manage/',{method:'DELETE',token:session.access_token,body:JSON.stringify({id:vendor.id})})
   setAdminVendors(old=>old.filter(item=>item.id!==vendor.id))
   await Promise.all([refreshSellerDashboard(),load()])
   notify('Vendor deleted')
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
  if(!window.confirm(`Permanently delete order ${order.order_number}? This permanently removes the order record and cannot be undone.`))return
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
  if(profile?.role==='admin'&&!authUsersFetched)await fetchAuthUsers()
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
  else if(currentProfile?.role==='delivery_boy')setDrawer('delivery-dashboard')
  else setDrawer('account')
 }
 function startNewProduct(){
  const firstStore=sellerDashboard?.stores?.find(s=>s.status==='approved')
  setProductForm({name:'',description:'',additional_description:'',price:'',compare_at_price:'',category_id:'',vendor_id:profile?.role==='admin'?'':(firstStore?.id||''),image_url:'',image_public_id:'',extra_images:[],sizes:'S,M,L,XL',size_prices:'',colors:'Black,Blue',stock_quantity:'1'})
  setDrawer('manage')
 }
 function startEditProduct(product){
  setProductForm({id:product.id,name:product.name||'',description:product.description||'',additional_description:product.additional_description||'',price:String(product.price??''),compare_at_price:product.compare_at_price==null?'':String(product.compare_at_price),category_id:product.category_id||'',vendor_id:product.vendor_id||'',image_url:product.image_url||'',image_public_id:product.image_public_id||'',extra_images:Array.isArray(product.extra_images)?product.extra_images:[],sizes:(product.sizes||[]).join(','),size_prices:(product.sizes||[]).map(s=>product.size_prices?.[s]??'').join(','),colors:(product.colors||[]).join(','),stock_quantity:String(product.stock_quantity??0)})
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
   const payload={...productForm,additional_description:productForm.additional_description||'',extra_images:productForm.extra_images.map((image,index)=>({...image,sort_order:index,alt_text:image.alt_text||productForm.name})),price:Number(productForm.price),compare_at_price:productForm.compare_at_price?Number(productForm.compare_at_price):null,stock_quantity:Number(productForm.stock_quantity),sizes:productForm.sizes.split(',').map(x=>x.trim()).filter(Boolean),size_prices:(()=>{const sizes=productForm.sizes.split(',').map(x=>x.trim()).filter(Boolean);const values=productForm.size_prices.split(',').map(x=>x.trim()).filter(x=>x!=='');if(!values.length)return {};if(values.length!==1&&values.length!==sizes.length)throw new Error('Enter one size price for all sizes, or one price per size in the same order.');const prices=values.length===1?sizes.map(()=>values[0]):values;return Object.fromEntries(sizes.map((s,i)=>[s,Number(prices[i])]))})(),colors:productForm.colors.split(',').map(x=>x.trim()).filter(Boolean)}
   await api('/products/manage/',{method:productForm.id?'PATCH':'POST',token:session.access_token,body:JSON.stringify(payload)})
   setProductForm({name:'',description:'',additional_description:'',price:'',compare_at_price:'',category_id:'',vendor_id:'',image_url:'',image_public_id:'',extra_images:[],sizes:'S,M,L,XL',size_prices:'',colors:'Black,Blue',stock_quantity:'1'})
   await load();await refreshSellerDashboard();setDrawer('seller-dashboard');notify(productForm.id?'Product updated':'Product created')
  }catch(e){notify(e.message)}finally{setBusy(false)}
 }
 async function place(e){
  e.preventDefault();if(busy)return
  if(subtotal<MINIMUM_ORDER_AMOUNT){notify(`Minimum order amount is ${money(MINIMUM_ORDER_AMOUNT)}. Add ${money(MINIMUM_ORDER_AMOUNT-subtotal)} more to continue.`);setDrawer('cart');return}
  if(!session)return login()
  if(!address.id)return notify('Choose a saved delivery address before placing your order.')
  if(vendors.length>1)return notify('Checkout one seller at a time.')
  setBusy(true)
  try{
   // Use the address and drop-off contact entered for THIS order only.
   // Never read or substitute a customer profile/default/saved address.
   const checkoutAddress={...address}
   const phone=String(checkoutAddress.phone||'').trim()
   const phoneDigits=phone.replace(/[^0-9]/g,'').length
   if(!String(checkoutAddress.recipient_name||'').trim()||!String(checkoutAddress.line1||'').trim()||! /^[0-9+() \\-]{10,16}$/.test(phone)||phoneDigits<10||phoneDigits>15)return notify('Address incomplete: enter drop-off recipient name, a valid 10–15 digit mobile number, and house/street address.')
   const latitude=Number(checkoutAddress.latitude),longitude=Number(checkoutAddress.longitude)
   if(checkoutAddress.latitude===''||checkoutAddress.longitude===''||checkoutAddress.latitude==null||checkoutAddress.longitude==null||!Number.isFinite(latitude)||!Number.isFinite(longitude)||latitude < -90||latitude > 90||longitude < -180||longitude > 180)return notify('Address incomplete: select a valid delivery location on the map or use your current location.')
   // Quote against the coordinates entered for this order.
   const checkoutQuote=await api('/delivery/quote/',{method:'POST',token:session.access_token,body:JSON.stringify({vendor_id:cart[0]?.vendor_id,latitude,longitude})})
   if(!checkoutQuote||checkoutQuote.vendor_id!==cart[0]?.vendor_id)return notify('Could not verify delivery for this address. Please review the pin and retry.')
   const payload={...checkoutAddress,city:'Rayachoty',state:'Andhra Pradesh',latitude:Number(checkoutAddress.latitude),longitude:Number(checkoutAddress.longitude)}
   const r=await api('/orders/',{method:'POST',token:session.access_token,body:JSON.stringify({address:{...payload,saved_address_id:checkoutAddress.id},notes:orderNotes,items:cart.map(i=>({product_id:i.id,quantity:i.quantity,size:i.size,color:i.color}))})})
   const fallbackItems=cart.map(i=>({product_id:i.id,product_name:i.name,image_url:i.image_url,quantity:i.quantity,size:i.size,color:i.color,unit_price:i.price,line_total:Number(i.price)*i.quantity}))
   let createdOrder={...r,address_snapshot:r.address_snapshot||payload,items:fallbackItems}
   // Prefer the persisted server-side order representation for the details screen.
   // If the follow-up read fails, the successful POST response remains sufficient.
   try{
    const persisted=await api('/orders/',{token:session.access_token})
    const persistedRows=Array.isArray(persisted.results)?persisted.results:(Array.isArray(persisted)?persisted:[])
    const match=persistedRows.find(item=>String(item.id)===String(r.id))
    if(match)createdOrder={...createdOrder,...match,address_snapshot:match.address_snapshot||createdOrder.address_snapshot,items:Array.isArray(match.items)?match.items:fallbackItems}
   }catch(readError){console.warn('Order created, but the refreshed order details could not be loaded:',readError.message)}
   setCart([]);setAddress({recipient_name:'',phone:'',line1:'',line2:'',landmark:'',city:'Rayachoty',state:'Andhra Pradesh',postal_code:'',latitude:'',longitude:'',notes:'',id:''});setOrderNotes('');setOrders(o=>[createdOrder,...o.filter(item=>String(item.id)!==String(createdOrder.id))]);setSelectedOrder(createdOrder);setOrderReturnDrawer('orders');setDeliveryQuote(null);setDrawer('order-details');notify(`Order ${r.order_number} placed successfully`)
  }catch(err){notify(err.message)}finally{setBusy(false)}
 }
 const byCatalogOrder = (a,b) => (Number(a.sort_order??0)-Number(b.sort_order??0)) || (String(a.created_at||'').localeCompare(String(b.created_at||''))) || String(a.name||'').localeCompare(String(b.name||''),'en',{sensitivity:'base'})
 const topLevelCategories = categories.filter(c=>c.slug!=='all'&&!c.parent_id).sort(byCatalogOrder)
 const getChildren = parentId => categories.filter(c=>String(c.parent_id||'')===String(parentId||'')).sort(byCatalogOrder)
 const chooseCategory = cat => { recordInterest(cat,'category'); setCategory(cat.slug); setMobileActive('shop') }
 const catalogContent = <>
  {error&&<div className="notice">{error}<button onClick={()=>load(new AbortController().signal)}>Retry</button></div>}
  <div className="grid">{loading?Array.from({length:6},(_,i)=><div className="skeleton" key={i}><div/></div>):products.map((p,i)=><article className="product" key={p.id}><button className="photo" onClick={()=>openProductDetails(p)}>{p.image_url?<img src={p.image_url} alt={p.name} loading={i>2?'lazy':'eager'} onError={e=>{e.currentTarget.style.display='none';e.currentTarget.parentElement.classList.add('image-failed')}}/>:<span className="placeholder">BF</span>}{p.compare_at_price&&Number(p.compare_at_price)>Number(p.price)&&<small className="sale">SPECIAL PRICE</small>}<span className="quick">Quick view <FiArrowRight size={13}/></span></button><div className="product-info"><div className="meta"><span>{p.category_name||'Curated style'}</span></div><button className="product-name" onClick={()=>openProductDetails(p)}>{p.name}</button><div className="price"><b>{money(p.price)}</b>{p.compare_at_price&&Number(p.compare_at_price)>Number(p.price)&&<del>{money(p.compare_at_price)}</del>}<button onClick={()=>openProductDetails(p)} aria-label={'Choose options for '+p.name}><FiPlus size={18}/></button></div></div></article>)}</div>
   {!loading&&!error&&products.length>0&&<div className="catalog-pagination" style={{display:"flex",flexDirection:"column",alignItems:"center",gap:"10px",padding:"24px"}}><small>{hasMore?'Showing '+products.length+' products':'Showing all '+products.length+' products'}</small>{hasMore&&<button type="button" className="secondary" onClick={()=>{if(!loadingMore&&nextOffset!==null)load(undefined,nextOffset,true)}} disabled={loadingMore||nextOffset===null}>{loadingMore?'Loading more styles…':'Load more styles'}</button>}</div>}
  {!loading&&!error&&!products.length&&<div className="empty"><FiShoppingBag size={27}/><h3>No products here yet</h3><p>Try another category or clear your search to see all available styles.</p><button className="secondary" onClick={()=>{setCategory('all');setSearch('');setMobileActive('home')}}>Show all styles</button></div>}
 </>

 return <div className="site app-shell">
  <aside className="app-sidebar">
   <button className="brand app-brand" onClick={()=>{setCategory('all');setSearch('');setMobileActive('home')}}><img className="logo-image" src="/b-tech-logo.png" alt="B Tech logo" /><span><b>BALA FASHION</b><small>RAYACHOTY</small></span></button>
   <div className="sidebar-caption">YOUR STORE</div>
   <nav className="sidebar-nav" aria-label="App navigation">
    <button className={mobileActive==='home'?'active':''} onClick={()=>{setDrawer('');setMobileActive('home');setCategory('all');setSearch('')}}><FiHome size={19}/><span>Home</span></button>
    <button className={mobileActive==='categories'?'active':''} onClick={()=>{setDrawer('');setMobileActive('categories');setCategory('all')}}><FiGrid size={19}/><span>Categories</span></button>
    <button className={mobileActive==='shop'?'active':''} onClick={()=>{setDrawer('');setMobileActive('shop');setCategory('all');setSearch('')}}><FiShoppingBag size={19}/><span>Shop all</span></button>
    <button className={mobileActive==='bag'?'active':''} onClick={()=>{setMobileActive('bag');setDrawer('cart')}}><FiShoppingBag size={19}/><span>My bag</span>{count>0&&<b className="sidebar-count">{count}</b>}</button>
    <button className={mobileActive==='account'?'active':''} onClick={openAccountEntry}><FiUser size={19}/><span>Account</span></button>
   </nav>
   <div className="sidebar-bottom"><span className="status-dot"/><span>Rayachoty store</span><small>Local fashion · COD</small></div>
  </aside>
  <div className="app-workspace">
   <header className="app-topbar">
    <div className="app-mobile-brand"><img className="logo-image" src="/b-tech-logo.png" alt="B Tech logo" /><span><b>BALA FASHION</b><small>RAYACHOTY</small></span></div>
    <div className="app-breadcrumb"><span>Store</span><FiArrowRight size={14}/><b>{({home:'Overview',categories:'Categories',shop:'All products',search:'Search results',bag:'Your bag',account:'Account'})[mobileActive]||'Overview'}</b></div>
    <label className="app-search"><FiSearch size={18}/><input ref={searchInputRef} aria-label="Search clothing" placeholder="Search products, styles..." value={search} onFocus={()=>{setDrawer('');setMobileActive('search')}} onChange={e=>{setDrawer('');setSearch(e.target.value);setMobileActive('search')}}/><kbd>⌕</kbd></label>
    <div className="notification-area">
      <button className={'notification-bell'+(notificationOpen?' is-open':'')} type="button" onClick={openNotifications} aria-label={unreadNotificationCount?'Notifications, '+unreadNotificationCount+' unread':'Notifications'} aria-expanded={notificationOpen} title="Notifications">
       <FiBell size={19}/>{unreadNotificationCount>0&&<span className="notification-count">{unreadNotificationCount>99?'99+':unreadNotificationCount}</span>}
      </button>
      {notificationOpen&&<section className="notification-popover" aria-label="Notifications">
       <div className="notification-popover-head"><div><b>Notifications</b><small>{unreadNotificationCount?unreadNotificationCount+' unread':'You’re all caught up'}</small></div><div className="notification-head-actions">{unreadNotificationCount>0&&<button type="button" onClick={markAllNotificationsRead}>Mark all read</button>}<button type="button" className="notification-close" aria-label="Close notifications" onClick={()=>setNotificationOpen(false)}><FiX size={16}/></button></div></div>
       {!notifications.length?<div className="notification-empty"><span className="notification-empty-icon"><FiBell size={22}/></span><b>No notifications yet</b><p>Only order placed and delivered updates appear here.</p></div>:
        <div className="notification-list">{notifications.map(item=><button key={item.id} type="button" className={'notification-item'+(item.read?' read':'')} onClick={()=>openNotificationOrder(item)}><span className="notification-item-mark"><FiBell size={15}/></span><span className="notification-item-copy"><b>{item.title}</b><small>{item.body}</small><time>{new Date(item.createdAt).toLocaleString('en-IN',{dateStyle:'medium',timeStyle:'short'})}</time></span>{!item.read&&<i className="notification-unread-dot"/>}</button>)}</div>}
      </section>}
     </div>
     <button className="app-account-button" onClick={openAccountEntry}>{session?.user?.user_metadata?.avatar_url?<img src={session.user.user_metadata.avatar_url} alt="Profile"/>:<FiUser size={18}/>}<span>{(session?.user?.user_metadata?.full_name||session?.user?.user_metadata?.name||session?.user?.email?.split('@')[0])?.split(' ')[0]||'Sign in'}</span></button>
   </header>
   <main className="app-main">
    {mobileActive==='home'&&<div className="app-page app-home-page">
     <section className="home-greeting"><div><div className="home-location"><span className="home-live-dot"/><span>RAYACHOTY · LOCAL FASHION</span></div><h1>{(session?.user?.user_metadata?.full_name||session?.user?.user_metadata?.name||session?.user?.email?.split('@')[0])?('Hey, '+(session.user.user_metadata.full_name||session.user.user_metadata.name||session.user.email.split('@')[0]).split(' ')[0]+' 👋'):'Hey there 👋'}<br/><em>Find your style.</em></h1><p>Everyday looks, closer to home.</p></div></section>
     <label className="home-search-shortcut"><FiSearch size={18}/><input aria-label="Search styles" placeholder="Search clothes, styles and more..." value={search} onFocus={()=>setMobileActive('search')} onChange={e=>{setSearch(e.target.value);setMobileActive('search')}}/><FiArrowRight size={17}/></label>
     <button className="app-promo home-promo" onClick={()=>setMobileActive('categories')}><span className="app-promo-copy"><small>THE RAYACHOTY EDIT</small><b>Good looks.<br/>Good days.</b><span>Explore collections <FiArrowRight size={15}/></span></span><span className="app-promo-image">{categories.find(c=>c.slug!=='all'&&c.image_url)?.image_url?<img src={categories.find(c=>c.slug!=='all'&&c.image_url).image_url} alt="Featured category"/>:<span className="home-promo-monogram">BF</span>}</span></button>
     <div className="home-quick-actions"><button onClick={()=>{setCategory('all');setSearch('');setMobileActive('shop')}}><span className="home-action-icon"><FiShoppingBag size={18}/></span><span><b>Shop all</b><small>Explore the collection</small></span><FiArrowRight size={16}/></button><button onClick={getOrders}><span className="home-action-icon"><FiTruck size={18}/></span><span><b>My orders</b><small>View your purchases</small></span><FiArrowRight size={16}/></button></div>
     <section className="app-section home-categories-section"><div className="app-section-head"><div><h2>Main categories</h2><p>Tap a category to explore its subcategories</p></div><button onClick={()=>{setFocusedMainCategory('');setCategorySearch('');setMobileActive('categories')}}>See all <FiArrowRight size={15}/></button></div>
      <div className="home-main-category-grid">{topLevelCategories.map((c,i)=><button type="button" className="home-main-category-link" key={c.id||c.slug} aria-label={'Open '+c.name+' subcategories'} onClick={()=>{setFocusedMainCategory(String(c.id));setCategorySearch('');setMobileActive('categories')}}>
        <span className={'home-main-category-image tone-'+(i%5)}>{c.image_url?<img src={c.image_url} alt="" loading="lazy"/>:<span aria-hidden="true">{c.name}</span>}</span>
        <span className="home-main-category-name">{c.name}</span>
      </button>)}</div>
     </section>
     <section className="app-section home-recommendations-section"><div className="app-section-head"><div><h2>Picked for you</h2><p>{interestSignals.length?'Based on the styles and categories you explore':'Explore products to personalize your picks'}</p></div><button type="button" onClick={()=>{setCategory('all');setSearch('');setFocusedMainCategory('');setMobileActive('shop')}}>View all <FiArrowRight size={15}/></button></div>{recommendationLoading&&!recommendationCatalog.length?<div className="recommendation-loading">Finding styles for you…</div>:recommendedProducts.length?<div className="recommendation-grid">{recommendedProducts.map((p,i)=><article className="product recommendation-product" key={p.id}><button type="button" className="photo" onClick={()=>openProductDetails(p)} aria-label={'View '+p.name}>{p.image_url?<img src={p.image_url} alt={p.name} loading="lazy"/>:<span className="placeholder">BF</span>}</button><div className="product-info"><div className="meta"><span>{p.category_name||'Curated style'}</span></div><button type="button" className="product-name" onClick={()=>openProductDetails(p)}>{p.name}</button><div className="price"><b>{money(p.price)}</b><button type="button" onClick={()=>openProductDetails(p)} aria-label={'Choose options for '+p.name}><FiPlus size={18}/></button></div></div></article>)}</div>:<p className="recommendation-loading">More recommendations will appear as products become available.</p>}</section>
     <section className="app-section home-products-section"><div className="app-section-head"><div><h2>Explore styles</h2><p>Live products from local sellers</p></div><button onClick={()=>{setCategory('all');setSearch('');setFocusedMainCategory('');setMobileActive('shop')}}>View all <FiArrowRight size={15}/></button></div>{catalogContent}</section>
    </div>}
    {mobileActive==='categories'&&<div className="app-page"><section className="page-intro"><div className="eyebrow muted">DISCOVER LOCAL SHOPPING</div><h1>{topLevelCategories.find(c=>String(c.id)===focusedMainCategory)?.name||'Categories'}</h1><p>{focusedMainCategory?'Choose a subcategory image to open its products and filters.':'Choose a main category to browse its subcategory images.'}</p></section>
     <label className="category-page-search"><FiSearch size={17}/><input value={categorySearch} onChange={e=>setCategorySearch(e.target.value)} placeholder="Filter categories…" aria-label="Filter categories"/>{categorySearch&&<button type="button" onClick={()=>setCategorySearch('')} aria-label="Clear category filter"><FiX size={15}/></button>}</label>
     <section className="category-screen-section">{categoriesError&&<div className="notice">{categoriesError}<button type="button" onClick={()=>{setCategoriesError('');setCategoriesLoading(true);api('/categories/').then(rows=>{if(!Array.isArray(rows))throw new Error('Invalid categories response');setCategories([defaultCats[0],...rows.filter(c=>c&&c.id&&c.slug&&c.is_active!==false)]);setCategoriesError('')}).catch(()=>setCategoriesError('Categories could not be loaded from the live catalog. Check the connection and retry.')).finally(()=>setCategoriesLoading(false))}}>Retry</button></div>}{categoriesLoading&&<div className="category-loading-note">Loading live categories…</div>}
      {focusedMainCategory?(()=>{const parent=topLevelCategories.find(c=>String(c.id)===focusedMainCategory);const children=parent?getChildren(parent.id).filter(child=>child.name.toLowerCase().includes(categorySearch.trim().toLowerCase())):[];return <><div className="category-screen-heading"><div><h2>{parent?.name||'Subcategories'}</h2><p>{children.length} subcategories</p></div><button type="button" onClick={()=>{setFocusedMainCategory('');setCategorySearch('')}}><FiChevronLeft size={14}/> All categories</button></div><div className="subcategory-image-grid">{children.map((child,i)=><button type="button" className="subcategory-image-card" key={child.id||child.slug} aria-label={'Open '+child.name+' products'} title={child.name} onClick={()=>chooseCategory(child)}><span className={'subcategory-image-media tone-'+(i%5)}>{child.image_url||parent?.image_url?<img src={child.image_url||parent?.image_url} alt={child.name} loading="lazy"/>:<span className="category-image-placeholder">{child.name}</span>}</span></button>)}</div>{!children.length&&<div className="empty category-filter-empty"><h3>No matching subcategories</h3><button className="secondary" onClick={()=>setCategorySearch('')}>Clear filter</button></div>}</>})():<><div className="category-screen-heading"><div><h2>Main categories</h2><p>{topLevelCategories.filter(c=>c.name.toLowerCase().includes(categorySearch.trim().toLowerCase())||getChildren(c.id).some(child=>child.name.toLowerCase().includes(categorySearch.trim().toLowerCase()))).length} categories</p></div><button type="button" onClick={()=>{setCategory('all');setMobileActive('shop')}}>All products <FiArrowRight size={14}/></button></div><div className="app-category-grid">{topLevelCategories.filter(c=>c.name.toLowerCase().includes(categorySearch.trim().toLowerCase())||getChildren(c.id).some(child=>child.name.toLowerCase().includes(categorySearch.trim().toLowerCase()))).map((c,i)=><button type="button" className="app-category-card" key={c.id||c.slug} aria-label={'Open '+c.name+' subcategories'} onClick={()=>setFocusedMainCategory(String(c.id))}><span className={'app-category-card-image tone-'+(i%5)}>{c.image_url?<img src={c.image_url} alt="" loading="lazy"/>:<span aria-hidden="true">{c.name}</span>}</span><span className="category-card-title">{c.name}</span><span className="subcategory-image-action">Browse subcategories <FiArrowRight size={13}/></span></button>)}</div></>}
     </section></div>}
    {mobileActive==='shop'&&<div className="app-page"><section className="page-intro"><div className="eyebrow muted">THE COLLECTION</div><h1>{categories.find(c=>c.slug===category)?.name||'All products'}</h1><p>Use the main category filter, then choose a subcategory when available.</p></section>
     <section className="shop-filter-panel" aria-label="Product category filters"><div className="shop-filter-heading"><h2>Main categories</h2><span>{topLevelCategories.length} available</span></div><div className="app-filter-row"><button className={category==='all'?'active':''} onClick={()=>setCategory('all')}>All products</button>{topLevelCategories.map(c=><button className={category===c.slug?'active':''} key={c.id||c.slug} onClick={()=>setCategory(c.slug)}>{c.name}</button>)}</div>
      {(()=>{const selectedCategory=categories.find(c=>c.slug===category);const selectedParent=selectedCategory?.parent_id?categories.find(c=>String(c.id)===String(selectedCategory.parent_id)):selectedCategory;const children=selectedParent?getChildren(selectedParent.id):[];return children.length>0?<div className="shop-subcategory-filter"><div className="shop-filter-heading"><h3>{selectedParent.name} subcategories</h3><button type="button" onClick={()=>setCategory(selectedParent.slug)}>All {selectedParent.name}</button></div><div className="app-filter-row">{children.map(child=><button className={category===child.slug?'active':''} key={child.id||child.slug} onClick={()=>setCategory(child.slug)}>{child.name}</button>)}</div></div>:null})()}
     </section><div className="shop-results-heading"><h2>{category==='all'?'All products':(categories.find(c=>c.slug===category)?.name||'Products')}</h2><p>{search.trim()?'Matching your search':'Products available from approved local sellers'}</p></div>{catalogContent}</div>}
    {mobileActive==='search'&&<div className="app-page"><section className="page-intro"><div className="eyebrow muted">FIND YOUR FIT</div><h1>Search</h1><p>{search ? 'Results for “'+search+'”' : 'Search products by name, category or style.'}</p></section><label className="app-search-page-field"><FiSearch size={18}/><input type="search" aria-label="Search products by name, category or style" placeholder="Search clothes, styles and more…" value={search} onChange={event=>setSearch(event.target.value)}/>{search&&<button type="button" className="clear-search-button" aria-label="Clear search" onClick={()=>setSearch('')}><FiX size={16}/></button>}</label>{catalogContent}</div>}
    {mobileActive==='bag'&&<div className="app-page"><section className="page-intro"><div className="eyebrow muted">READY WHEN YOU ARE</div><h1>Your bag</h1><p>Your selected styles stay here while you shop.</p></section><button className="primary" onClick={()=>setDrawer('cart')}>Open bag <FiShoppingBag size={17}/>{count>0&&<span>({count})</span>}</button></div>}
    {mobileActive==='account'&&<div className="app-page"><section className="page-intro"><div className="eyebrow muted">YOUR PROFILE</div><h1>Account</h1><p>Manage your profile, orders and store tools.</p></section><div className="app-account-card"><div className="app-account-avatar"><FiUser size={24}/></div><div><b>{session?.user?.user_metadata?.full_name||session?.user?.user_metadata?.name||session?.user?.email||'Welcome to Bala Fashion'}</b><small>{profile?.role||'Sign in to access your account'}</small></div></div><button className="primary" onClick={openAccountEntry}>{session?(['vendor','admin'].includes(profile?.role)?'Open management dashboard':'Open account'):'Continue with Google'} <FiArrowRight size={16}/></button>{session&&<button className="secondary app-orders-button" onClick={getOrders}>View my orders</button>}</div>}
   </main>
    <nav className="mobile-bottom-nav" aria-label="Primary app navigation">
     <button className={`mobile-nav-item${mobileActive==='home'?' active':''}`} aria-current={mobileActive==='home'?'page':undefined} onClick={()=>navigateMobilePage('home')}><FiHome size={20}/><span>Home</span></button>
     <button className={`mobile-nav-item${mobileActive==='categories'?' active':''}`} aria-current={mobileActive==='categories'?'page':undefined} onClick={()=>navigateMobilePage('categories')}><FiGrid size={20}/><span>Categories</span></button>
     <button className={`mobile-nav-item${mobileActive==='search'?' active':''}`} aria-current={mobileActive==='search'?'page':undefined} onClick={()=>navigateMobilePage('search')}><FiSearch size={20}/><span>Search</span></button>
     <button className={`mobile-nav-item${mobileActive==='bag'?' active':''}`} aria-current={mobileActive==='bag'?'page':undefined} onClick={()=>navigateMobilePage('bag')}><span className="mobile-bag-icon"><FiShoppingBag size={20}/>{count>0&&<b>{count>99?'99+':count}</b>}</span><span>Bag</span></button>
     <button className={`mobile-nav-item${mobileActive==='account'?' active':''}`} aria-current={mobileActive==='account'?'page':undefined} onClick={()=>navigateMobilePage('account')}><FiUser size={20}/><span>Account</span></button>
    </nav>
  </div>
  {drawer&&<div className="overlay" onMouseDown={e=>e.target===e.currentTarget&&setDrawer('')}><aside className="drawer"><div className="drawer-head"><div><div className="eyebrow muted">{drawer==='cart'?'YOUR SELECTION':drawer==='checkout'?'DELIVERY DETAILS':drawer==='orders'||drawer==='order-details'?'YOUR ACCOUNT':'BALA FASHION'}</div><h2>{({cart:'Your bag',checkout:'Checkout',orders:'My orders','order-details':'Order details',account:'Account',addresses:'Saved addresses','categories-manage':'Manage categories','vendors-manage':'Manage vendors','delivery-management':'Delivery staff','delivery-dashboard':'Delivery dashboard'})[drawer]||'Manage products'}</h2></div><button className="icon" onClick={()=>setDrawer('')}><FiX/></button></div>
   {drawer==='cart'&&<div className="drawer-body">{!cart.length?<div className="empty"><FiShoppingBag/><h3>Your bag is taking a break.</h3><p>Find a piece you love and add it here.</p><button className="primary" onClick={()=>setDrawer('')}>Keep exploring</button></div>:<>{cart.map(i=><div className="cart-item" key={i.key}><img src={i.image_url} alt={i.name}/><div><b>{i.name}</b><small>{i.size} {i.color&&`· ${i.color}`}</small><strong>{money(i.price)}</strong><div className="qty"><button onClick={()=>setCart(c=>c.map(x=>x.key===i.key?{...x,quantity:Math.max(1,x.quantity-1)}:x))}><FiMinus size={13}/></button>{i.quantity}<button onClick={()=>setCart(c=>c.map(x=>x.key===i.key?{...x,quantity:Math.min(Number(x.stock_quantity||20),x.quantity+1)}:x))}><FiPlus size={13}/></button><button className="remove" onClick={()=>setCart(c=>c.filter(x=>x.key!==i.key))}>Remove</button></div></div></div>)}{vendors.length>1&&<div className="warning">Please check out one seller at a time.</div>}{subtotal<MINIMUM_ORDER_AMOUNT&&<div className="warning">Minimum order amount is {money(MINIMUM_ORDER_AMOUNT)}. Add {money(MINIMUM_ORDER_AMOUNT-subtotal)} more to continue.</div>}<div className="summary"><div><span>Subtotal</span><b>{money(subtotal)}</b></div><small>Cash on delivery · Rayachoty service area</small><button className="primary full" disabled={vendors.length>1||subtotal<MINIMUM_ORDER_AMOUNT} onClick={()=>session?setDrawer('checkout'):setDrawer('account')}>Continue to checkout <FiArrowRight size={16}/></button></div></>}</div>}
   {drawer==='checkout'&&<form className="drawer-body form" onSubmit={place}>
    <p>Delivery is available only in Rayachoty. The final distance and fee are calculated on the server using the road route from this store.</p>
     <p>Checkout uses a saved delivery address. The server reads the selected address from your account and freezes its details and map pin into this order when you place it.</p>
    {address.id?<section className="notice">
     <b>Delivery address {address.is_default?'· Default':''}</b>
     <p>{address.recipient_name} · {address.phone}</p>
     <p>{[address.line1,address.line2,address.landmark,address.city,address.state,address.postal_code].filter(Boolean).join(', ')}</p>
     <p>Saved map pin: {address.latitude}, {address.longitude}</p>
     <button type="button" className="secondary full" onClick={()=>{setAddressReturnDrawer('checkout');setDrawer('addresses')}}>Change saved address</button>
    </section>:<section className="notice">
     <b>Select a saved delivery address</b>
     <p>Your default address is selected automatically. If you have not saved an address yet, add one and select it here before placing the order.</p>
     <button type="button" className="secondary full" onClick={()=>{setAddressReturnDrawer('checkout');setDrawer('addresses')}}>Choose or add saved address</button>
    </section>}
    <div className="local-service-note"><FiMapPin size={16}/> Rayachoty, Andhra Pradesh · Maximum 5 km road distance from the selling vendor</div>
    <div className="delivery-fee-preview">
     {deliveryQuoteLoading?<span>Calculating road route and delivery charge…</span>:deliveryQuoteError?<span className="location-error">{deliveryQuoteError}</span>:deliveryQuote?<><div><span>Road distance · {deliveryQuote.distance_km} km</span><b>{money(deliveryQuote.delivery_fee)}</b></div><small>₹5 per started 500 metres · maximum 5 km road distance · OpenStreetMap-compatible routing</small></>:<span>{deliveryAddressComplete(address)?'Calculating delivery fee for this order location…':'Enter the drop-off details and select a map pin to calculate delivery.'}</span>}
    </div>
    <label>Delivery notes<textarea rows="2" maxLength={500} value={orderNotes} onChange={e=>setOrderNotes(e.target.value)}/></label>
    <div className="cod"><FiCheck size={17}/><span><b>Cash on delivery</b><small>Pay in cash when your order arrives.</small></span></div>
    <div className="summary">
     {subtotal<MINIMUM_ORDER_AMOUNT&&<div className="warning">Minimum order amount is {money(MINIMUM_ORDER_AMOUNT)}. Add {money(MINIMUM_ORDER_AMOUNT-subtotal)} more to place your order.</div>}
     <div><span>Items subtotal</span><b>{money(subtotal)}</b></div>
     <div><span>Delivery charge</span><b>{deliveryQuote?money(deliveryQuote.delivery_fee):'Calculate route first'}</b></div>
     <div><span>Total</span><b>{deliveryQuote?money(subtotal+Number(deliveryQuote.delivery_fee)):'—'}</b></div>
     <button className="primary full" disabled={busy||!deliveryAddressComplete(address)||subtotal<MINIMUM_ORDER_AMOUNT||!deliveryQuote||deliveryQuoteLoading}>{busy?'Placing order…':'Place COD order'} <FiArrowRight size={16}/></button>
    </div>
   </form>}
   {drawer==='orders'&&<div className="drawer-body account-orders-panel">{!session?<div className="empty"><p>Sign in to see your orders.</p><button className="primary" onClick={()=>setDrawer('account')}>Sign in to continue</button></div>:!orders.length?<div className="empty"><FiPackage size={28}/><h3>No orders yet</h3><p>Your orders will appear here after checkout.</p><button className="secondary" onClick={getOrders}>Refresh orders</button></div>:<><div className="orders-intro"><span className="orders-intro-icon"><FiPackage size={20}/></span><div><b>Your order history</b><small>{orders.length} order{orders.length===1?'':'s'} · Latest first</small></div><button className="secondary" onClick={getOrders}>Refresh</button></div>{orders.map(o=><button type="button" className="account-order-card" key={o.id} onClick={()=>openOrderDetails(o)}><span className="account-order-thumb">{o.items?.[0]?.image_url?<img src={o.items[0].image_url} alt=""/>:<FiPackage size={21}/>}</span><span className="account-order-main"><b>{o.order_number}</b><small>{new Date(o.created_at).toLocaleDateString('en-IN',{dateStyle:'medium'})} · {o.items?.length||0} item line{(o.items?.length||0)===1?'':'s'}</small><span className={'order-status-chip status-'+String(o.status||'placed').replaceAll('_','-')}>{String(o.status||'placed').replaceAll('_',' ')}</span></span><span className="account-order-total"><b>{money(o.total)}</b><small>View details <FiArrowRight size={12}/></small></span></button>)}</>}</div>}
   {drawer==='order-details'&&<div className="drawer-body order-detail-page">{!selectedOrder?<div className="empty"><p>Choose an order to view its details.</p><button className="secondary" onClick={getOrders}>Back to orders</button></div>:<><button className="order-back" onClick={()=>setDrawer(orderReturnDrawer)}><FiChevronLeft size={17}/> Back</button><div className="order-detail-hero"><div className="order-detail-mark"><FiPackage size={23}/></div><div><span className={'order-status-chip status-'+String(selectedOrder.status||'placed').replaceAll('_','-')}>{String(selectedOrder.status||'placed').replaceAll('_',' ')}</span><h3>{selectedOrder.order_number}</h3><p><FiCalendar size={14}/> Placed {new Date(selectedOrder.created_at).toLocaleString('en-IN',{dateStyle:'medium',timeStyle:'short'})}</p></div></div><section className="order-detail-section"><div className="order-detail-section-title"><h3>Items in this order</h3><span>{selectedOrder.items?.reduce((sum,item)=>sum+Number(item.quantity||0),0)||0} pieces</span></div>{(selectedOrder.items||[]).map((item,index)=><div className="order-detail-item" key={item.product_id||item.product_name+index}><div className="order-detail-image">{item.image_url?<img src={item.image_url} alt={item.product_name||'Product'} onError={e=>{e.currentTarget.style.display='none'}}/>:<FiPackage size={19}/>}</div><div className="order-detail-item-copy"><b>{item.product_name||'Fashion item'}</b><small>{[item.size&&'Size '+item.size,item.color&&'Colour '+item.color].filter(Boolean).join(' · ')||'Standard option'}</small><small>Qty: {item.quantity} × {money(item.unit_price??(Number(item.line_total||0)/Math.max(1,Number(item.quantity||1))))}</small></div><strong>{money(item.line_total)}</strong></div>)}</section>{profile?.role!=='vendor'&&selectedOrderAddress&&<section className="order-detail-section"><div className="order-detail-section-title"><h3><FiMapPin size={17}/> {profile?.role==='admin'?'Order drop-off details':'Order drop-off address'}</h3></div>{selectedOrderAddress&&typeof selectedOrderAddress==='object'&&(selectedOrderAddress.line1||selectedOrderAddress.recipient_name)?<div className="delivery-address-card"><b>{selectedOrderAddress.recipient_name||'Recipient'}</b><p>{[selectedOrderAddress.line1,selectedOrderAddress.line2,selectedOrderAddress.landmark].filter(Boolean).join(', ')}</p><p>{[selectedOrderAddress.city,selectedOrderAddress.state,selectedOrderAddress.postal_code].filter(Boolean).join(', ')}</p>{selectedOrderAddress.phone&&<span><FiPhone size={14}/> Contact number: <a href={`tel:${selectedOrderAddress.phone}`}>{selectedOrderAddress.phone}</a></span>}{profile?.role==='customer'&&['out_for_delivery','delivered'].includes(selectedOrder.status)&&<div className="delivery-address-card customer-live-delivery-details"><b>Delivery staff</b><p>{selectedOrder.delivery_person_name||'Delivery person details are being updated.'}</p>{selectedOrder.delivery_person_phone&&<span><FiPhone size={14}/> <a href={`tel:${selectedOrder.delivery_person_phone}`}>{selectedOrder.delivery_person_phone}</a></span>}<b>Pickup details</b><p>{selectedOrder.vendor_name||'Vendor name unavailable'}</p><p>{selectedOrder.vendor_address||'Pickup address unavailable'}</p>{selectedOrder.vendor_phone&&<span><FiPhone size={14}/> <a href={`tel:${selectedOrder.vendor_phone}`}>{selectedOrder.vendor_phone}</a></span>}</div>}{['admin','delivery_boy'].includes(profile?.role)&&selectedOrder.customer_email&&<p><b>Customer email:</b> <a href={`mailto:${selectedOrder.customer_email}`}>{selectedOrder.customer_email}</a></p>}{profile?.role==='admin'&&<div className="delivery-address-card"><b>Assigned delivery person</b><p>{selectedOrder.delivery_person_name||'Not assigned'}</p>{selectedOrder.delivery_person_phone&&<span><FiPhone size={14}/> {selectedOrder.delivery_person_phone}</span>}</div>}{['admin','delivery_boy'].includes(profile?.role)&&<div className="delivery-address-card"><b>Vendor / pickup</b><p>{selectedOrder.vendor_name||'Vendor name unavailable'}</p><p>{selectedOrder.vendor_address||'Vendor address not provided'}</p>{selectedOrder.vendor_phone&&<span><FiPhone size={14}/> {selectedOrder.vendor_phone}</span>}</div>}{selectedOrderAddress.latitude!=null&&selectedOrderAddress.longitude!=null&&<p><a href={`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(selectedOrderAddress.latitude+','+selectedOrderAddress.longitude)}`} target="_blank" rel="noreferrer">Open delivery location in Maps</a></p>}</div>:<p className="order-detail-muted">No drop-off address was saved with this order.</p>}{profile?.role==='admin'&&!deliveryAddressComplete(selectedOrderAddress)&&<OrderAddressRepair session={session} order={selectedOrder} role={profile?.role} notify={notify} onSaved={snapshot=>setSelectedOrder(previous=>({...previous,address_snapshot:snapshot}))}/>}{selectedOrder.notes&&<p className="order-delivery-notes"><b>Delivery notes:</b> {selectedOrder.notes}</p>}</section>}<section className="order-detail-section"><div className="order-detail-section-title"><h3><FiCreditCard size={17}/> Payment & summary</h3></div><div className="order-payment-card"><div><span>Payment method</span><b>{String(selectedOrder.payment_method||'cod').toUpperCase()==='COD'?'Cash on delivery':String(selectedOrder.payment_method||'').toUpperCase()}</b></div><div><span>Payment status</span><b className={selectedOrder.payment_status==='paid'?'payment-success':'payment-pending'}>{selectedOrder.payment_status==='paid'?'Successful':String(selectedOrder.payment_status||'Pending').replaceAll('_',' ')}</b></div><div><span>Items subtotal</span><b>{money(selectedOrder.subtotal)}</b></div><div><span>Delivery fee</span><b>{money(selectedOrder.delivery_fee)}</b></div><div className="order-grand-total"><span>Total paid / due</span><b>{money(selectedOrder.total)}</b></div></div></section><section className="order-detail-section order-tracking-section"><div className="order-detail-section-title"><h3><FiClock size={17}/> Order progress</h3></div><div className="order-progress">{['placed','confirmed','packed','out_for_delivery','delivered'].map((status,index)=>{const states=['placed','confirmed','packed','out_for_delivery','delivered'];const current=states.indexOf(selectedOrder.status);const done=current>=index;return <div className={'order-progress-step'+(done?' done':'')+(selectedOrder.status==='cancelled'?' cancelled':'')} key={status}><span className="order-progress-dot">{done?<FiCheck size={12}/>:index+1}</span><div><b>{status.replaceAll('_',' ')}</b><small>{index===0?'Order received':index===1?'Seller confirmed':index===2?'Packed for dispatch':index===3?'On the way':'Delivered'}</small></div></div>})}{selectedOrder.status==='cancelled'&&<div className="order-cancelled-note">This order was cancelled.</div>}</div></section></>}</div>}
   {drawer==='account'&&(!session?<div className="drawer-body form auth-panel"><div className="auth-intro"><span className="auth-mark"><FiUser size={22}/></span><div className="eyebrow muted">BALA FASHION ACCOUNT</div><h3>{authMode==='forgot'?'Reset your password':authMode==='reset'?'Choose a new password':authMode==='signup'?'Create your account':'Welcome back'}</h3><p>{authMode==='forgot'?'We’ll email you a secure link to choose a new password.':authMode==='reset'?'Create a new password for your Bala Fashion account.':authMode==='signup'?'Join us to track orders and enjoy a smoother checkout.':'Sign in to track orders, save your details and shop your favourite styles.'}</p></div>{authMode!=='forgot'&&<><button className="primary full auth-google" type="button" onClick={login}><span className="google-g">G</span> Continue with Google <FiArrowRight size={16}/></button><div className="auth-divider"><span>or continue with email</span></div></>}<form className="form auth-form" onSubmit={authMode==='forgot'?sendPasswordReset:submitEmailAuth}><label>Email address<input className="auth-input" type="email" autoComplete="email" required value={authEmail} onChange={e=>setAuthEmail(e.target.value)} placeholder="you@example.com"/></label>{authMode!=='forgot'&&<label>Password<input className="auth-input" type="password" autoComplete={authMode==='signup'||authMode==='reset'?'new-password':'current-password'} minLength={6} required value={authPassword} onChange={e=>setAuthPassword(e.target.value)} placeholder="At least 6 characters"/></label>}{authMode==='signin'&&<button className="text auth-forgot" type="button" onClick={()=>setAuthMode('forgot')}>Forgot password?</button>}<button className="primary full auth-submit" disabled={authSubmitting}>{authSubmitting?'Please wait…':authMode==='forgot'?'Send reset link':authMode==='reset'?'Update password':authMode==='signup'?'Create account':'Sign in with email'} <FiArrowRight size={16}/></button>{authMode==='forgot'||authMode==='reset'?<button className="text full" type="button" onClick={()=>{setAuthMode('signin');setAuthPassword('')}}>Back to sign in</button>:<button className="text full auth-switch" type="button" onClick={()=>setAuthMode(m=>m==='signin'?'signup':'signin')}>{authMode==='signin'?"New to Bala Fashion? Create an account":'Already registered? Sign in'}</button>}</form><div className="auth-secure"><FiCheck size={14}/> Secure sign-in powered by Supabase</div></div>:<div className="drawer-body"><p>{session?.user?.user_metadata?.full_name||session?.user?.user_metadata?.name||session?.user?.email}</p><p className="muted">{profile?.role||'customer'}</p><button className="secondary full" onClick={getOrders}>View my orders</button>{(!profile?.role||profile?.role==='customer')&&<button className="secondary full" onClick={()=>{setAddressReturnDrawer('account');setDrawer('addresses')}}><FiMapPin size={16}/> Manage delivery addresses</button>}{['vendor','admin'].includes(profile?.role)&&<button className="primary full" onClick={openSellerDashboard}><FiLayout size={16}/> Seller dashboard</button>}{profile?.role==='admin'&&<button className="secondary full" onClick={openCategoryManagement}>Manage categories</button>}{profile?.role==='admin'&&<button className="secondary full" onClick={openVendorManagement}><FiShoppingBag size={16}/> Manage vendors</button>}{profile?.role==='admin'&&<button className="secondary full" onClick={openDeliveryManagement}><FiTruck size={16}/> Delivery staff</button>}{profile?.role==='delivery_boy'&&<button className="primary full" onClick={()=>setDrawer('delivery-dashboard')}><FiTruck size={16}/> Delivery dashboard</button>}<button className="text" onClick={logout}>Sign out</button></div>)}
   {drawer==='addresses'&&<AddressManagement session={session} notify={notify} returnTo={addressReturnDrawer} onChoose={(saved,returnTo)=>{if(returnTo==='checkout')setAddress({...saved,latitude:String(saved.latitude??''),longitude:String(saved.longitude??''),id:saved.id});setDrawer(returnTo);notify(returnTo==='checkout'?'Saved delivery address selected for this order.':'Saved address selected.')}}/>}
   {drawer==='seller-dashboard'&&<div className="drawer-body seller-dashboard">
    <div className="seller-dashboard-head"><div><b>{profile?.role==='admin'?'Management dashboard':'Seller dashboard'}</b><small>{sellerDashboard?.stores?.length||0} store(s) available to your account</small></div><div className="seller-dashboard-head-actions"><button className="secondary" onClick={refreshSellerDashboard} disabled={dashboardLoading}>{dashboardLoading?'Refreshing…':'Refresh'}</button><button className="secondary" onClick={logout}>Sign out</button></div></div>
    {dashboardLoading&&!sellerDashboard?<p>Loading your dashboard…</p>:<>
     {profile?.role==='admin'&&<><div className="seller-admin-actions"><button className="primary" onClick={openCategoryManagement}><FiGrid size={16}/> Manage categories</button><button className="secondary" onClick={openVendorManagement}><FiShoppingBag size={16}/> Manage vendors</button><button className="secondary" onClick={openDeliveryManagement}><FiTruck size={16}/> Delivery staff</button></div></>}
     <div className="seller-stat-grid"><div><b>{sellerDashboard?.stats?.products??0}</b><small>Products</small></div><div><b>{sellerDashboard?.stats?.active_products??0}</b><small>Published</small></div><div><b>{sellerDashboard?.stats?.low_stock??0}</b><small>Low stock</small></div><div><b>{sellerDashboard?.stats?.orders??0}</b><small>Recent orders</small></div></div>
     {sellerDashboard?.stores?.length>0&&<section className="seller-dashboard-section"><h3>{profile?.role==='admin'?'Stores you can manage':'Your store'}</h3>{sellerDashboard.stores.map(store=><div className="seller-store-row" key={store.id}><span><b>{store.name}</b><small>{store.slug}</small></span><span className={'seller-status '+store.status}>{store.status}</span></div>)}</section>}
     <section className="seller-dashboard-section seller-inventory-section"><div className="seller-section-title seller-inventory-header"><h3>Product inventory <small className="seller-inventory-count">{(sellerDashboard?.products||[]).filter(product=>[product.name,product.vendor_name,product.category_name,product.id].some(value=>String(value||'').toLowerCase().includes(sellerProductSearch.trim().toLowerCase()))).length} found</small></h3><button className="primary" onClick={startNewProduct} disabled={!sellerDashboard?.stores?.some(s=>s.status==='approved')}> <FiPlus size={15}/> Add product</button></div>
      {!!sellerDashboard?.products?.length&&<label className="seller-inventory-search"><FiSearch size={16}/><input type="search" aria-label="Search product inventory" placeholder="Search product name, store, category or ID…" value={sellerProductSearch} onChange={event=>setSellerProductSearch(event.target.value)} autoComplete="off"/>{!!sellerProductSearch&&<button type="button" className="text" onClick={()=>setSellerProductSearch('')} aria-label="Clear product search"><FiX size={15}/></button>}</label>}
      {!sellerDashboard?.products?.length?<p className="seller-empty">No products in your managed stores yet.</p>:<div className="seller-inventory-scroll" role="region" aria-label="Product inventory list" tabIndex="0">{sellerDashboard.products.filter(product=>[product.name,product.vendor_name,product.category_name,product.id].some(value=>String(value||'').toLowerCase().includes(sellerProductSearch.trim().toLowerCase()))).map(product=><article className="seller-product-row" key={product.id}><div className="seller-product-thumb">{product.image_url?<img src={product.image_url} alt={product.name}/>:<span>BF</span>}</div><div className="seller-product-main"><b>{product.name}</b><small>{product.vendor_name||'Store'} · {product.category_name||'Uncategorized'}</small><strong>{money(product.price)} · Stock {product.stock_quantity}</strong><span className={'seller-status '+(product.is_active?'approved':'suspended')}>{product.is_active?'Published':'Hidden'}</span></div><div className="seller-product-actions"><button className="secondary" aria-label={'Edit '+product.name} title="Edit product" onClick={()=>startEditProduct(product)}><FiEdit2 size={15}/></button>{product.is_active?<button className="secondary" aria-label={'Unpublish '+product.name} title="Hide product from storefront" onClick={()=>hideProduct(product)} disabled={busy}><FiEyeOff size={15}/></button>:<button className="secondary" aria-label={'Publish '+product.name} title="Publish product to storefront" onClick={()=>publishProduct(product)} disabled={busy}><FiEye size={15}/></button>}</div></article>)}{!sellerDashboard.products.some(product=>[product.name,product.vendor_name,product.category_name,product.id].some(value=>String(value||'').toLowerCase().includes(sellerProductSearch.trim().toLowerCase())))&&<p className="seller-empty seller-inventory-no-results">No products match “{sellerProductSearch}”. Try another name or category.</p>}</div>}
     </section>
     <section className="seller-dashboard-section"><div className="seller-section-title"><h3>Order management</h3><label className="order-search-field"><FiSearch size={15}/><input aria-label="Search orders" placeholder="Search order number or status" value={sellerOrderSearch} onChange={event=>setSellerOrderSearch(event.target.value)}/></label></div>{!sellerDashboard?.orders?.length?<p className="seller-empty">No orders yet.</p>:sellerDashboard.orders.slice(0,50).filter(order=>[order.order_number,order.status,order.payment_status,order.vendor_name].some(value=>String(value||'').toLowerCase().includes(sellerOrderSearch.trim().toLowerCase()))).map(order=><article className="seller-order-row" key={order.id}><span><button type="button" className="order-detail-link" onClick={()=>openOrderDetails(order,'seller-dashboard')}>{order.order_number} <FiArrowRight size={12}/></button><small>{new Date(order.created_at).toLocaleDateString('en-IN')}</small><small>{order.payment_method?.toUpperCase()||'COD'} · Payment: {order.payment_status==='paid'?'Successful':(order.payment_status||'Pending')}</small></span><span><b>{money(order.total)}</b><small>{String(order.status||'').replaceAll('_',' ')}</small><div className="seller-product-actions">{profile?.role==='vendor'&&(({placed:['confirmed','cancelled'],confirmed:['packed','cancelled']})[order.status]||[]).map(next=><button key={next} className="secondary" disabled={busy} onClick={()=>updateOrderStatus(order,next)}>{next.replaceAll('_',' ')}</button>)}{profile?.role==='admin'&&<button className="secondary" aria-label={`Delete order ${order.order_number}`} title="Permanently delete order" disabled={busy} onClick={()=>deleteOrder(order)}><FiTrash2 size={15}/><span>Delete</span></button>}</div></span></article>)}</section>
    </>}
   </div>}
   {drawer==='delivery-management'&&profile?.role==='admin'&&<div className="drawer-body seller-dashboard"><DeliveryManagement session={session} orders={sellerDashboard?.orders||[]} busy={busy} onRefresh={refreshSellerDashboard} notify={notify} authUsers={authUsers}/></div>}
   {drawer==='delivery-dashboard'&&profile?.role==='delivery_boy'&&<DeliveryDashboard session={session} notify={notify} onSignOut={logout} onOrderDetails={order=>openOrderDetails(order,'delivery-dashboard')}/>}
   {drawer==='categories-manage'&&<div className="drawer-body form">
     <p>Create and organize main categories and subcategories. Existing product references are preserved.</p>
     <form className="form" onSubmit={saveCategoryImage}>
      <h3>{categoryForm.category_id?'Edit category':'Add category'}</h3>
      <label>Category name<input required value={categoryForm.name} onChange={e=>setCategoryForm(p=>({...p,name:e.target.value}))} placeholder="e.g. Western Wear"/></label>
      <label>Parent category<select value={categoryForm.parent_id} onChange={e=>setCategoryForm(p=>({...p,parent_id:e.target.value}))}><option value="">None — main category</option>{adminCategories.filter(c=>c.id!==categoryForm.category_id&&c.is_active!==false).map(c=><option key={c.id} value={c.id}>{c.parent_id?'↳ ':''}{c.name}</option>)}</select><small>Choose None for a main category; choose a parent to create a subcategory.</small></label>
      <label>Sort order<input type="number" step="1" value={categoryForm.sort_order} onChange={e=>setCategoryForm(p=>({...p,sort_order:e.target.value}))}/></label>
      <label>Category image (optional, Cloudinary)<input type="file" accept="image/*" onChange={e=>uploadCategoryImage(e.target.files?.[0])}/></label>
      {categoryForm.image_url&&<img className="upload-preview" src={categoryForm.image_url} alt="Category image preview"/>}
      <div className="form-two"><button className="primary full" disabled={busy||!categoryForm.name.trim()}>{busy?'Saving…':categoryForm.category_id?'Save category':'Create category'}</button><button type="button" className="secondary full" onClick={()=>setCategoryForm({category_id:'',name:'',parent_id:'',image_url:'',sort_order:'0'})}>Clear</button></div>
     </form>
     <section className="seller-dashboard-section"><h3>All categories</h3>{!adminCategories.length?<p className="seller-empty">No categories found.</p>:adminCategories.map(cat=><article className={'seller-store-row'+(cat.parent_id?' category-child-row':'')} key={cat.id}><span><b>{cat.parent_id?'↳ ':''}{cat.name}</b><small>{cat.parent_name?'Under '+cat.parent_name+' · ':''}{cat.slug} · sort {cat.sort_order} · {cat.is_active?'Active':'Inactive'}</small></span><span className="seller-product-actions"><button className="secondary" onClick={()=>setCategoryForm({category_id:cat.id,name:cat.name,parent_id:cat.parent_id||'',image_url:cat.image_url||'',sort_order:String(cat.sort_order??0)})}><FiEdit2 size={15}/></button>{cat.is_active&&<button className="secondary" disabled={busy} onClick={()=>deactivateCategory(cat)}>Deactivate</button>}</span></article>)}</section>
    </div>}
   {drawer==='vendors-manage'&&<div className="drawer-body seller-dashboard"><div className="seller-section-title"><h3>Vendor management</h3><button className="secondary" onClick={openVendorManagement}>Refresh</button></div>
    <p>Select the existing website user by email. The selected account's Supabase UUID is verified by the backend before the vendor is created.</p>
    <form className="form admin-vendor-create" onSubmit={createVendor}>
     <h3>{vendorForm.id?'Update vendor delivery location':'Create vendor / store'}</h3>
     {!vendorForm.id&&<SearchableUserSelect users={authUsers} value={vendorForm.owner_user_id} onChange={id=>setVendorForm(p=>({...p,owner_user_id:id}))} label="Vendor owner" placeholder="Select a customer account" excludeRoles={['admin','vendor','delivery_boy']}/>}
     {vendorForm.id&&<label>Vendor owner email<input type="email" value={vendorForm.owner_email} readOnly/></label>}
     <label>Vendor / store name<input required maxLength="180" value={vendorForm.name} onChange={e=>setVendorForm(p=>({...p,name:e.target.value}))} placeholder="e.g. Bala Fashion Store" readOnly={Boolean(vendorForm.id)}/></label>
     <label>Contact phone<input value={vendorForm.phone} onChange={e=>setVendorForm(p=>({...p,phone:e.target.value}))} placeholder="Mobile number" readOnly={Boolean(vendorForm.id)}/></label>
     <label>Store address<textarea rows="2" value={vendorForm.address} onChange={e=>setVendorForm(p=>({...p,address:e.target.value}))} placeholder="Store address"/></label>
     {!vendorForm.id&&<><label>Description<textarea rows="2" value={vendorForm.description} onChange={e=>setVendorForm(p=>({...p,description:e.target.value}))} placeholder="Optional store description"/></label>
     <label>Initial status<select value={vendorForm.status} onChange={e=>setVendorForm(p=>({...p,status:e.target.value}))}><option value="pending">Pending approval</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="suspended">Suspended</option></select></label></>}
     <LocationPicker label="Vendor store location" latitude={vendorForm.latitude} longitude={vendorForm.longitude} onChange={({latitude,longitude})=>setVendorForm(p=>({...p,latitude,longitude}))}/>
     <button className="primary full" disabled={busy}>{busy?'Saving…':vendorForm.id?'Save vendor location':'Create vendor with map location'}</button>
     {vendorForm.id&&<button type="button" className="secondary full" onClick={()=>setVendorForm({id:'',owner_id:'',owner_email:'',owner_user_id:'',name:'',phone:'',address:'',description:'',latitude:'',longitude:'',status:'pending'})}>Cancel location edit</button>}
    </form>
    {!adminVendors.length?<p className="seller-empty">No vendor records found.</p>:adminVendors.map(v=><article className="seller-store-row" key={v.id}><span><b>{v.name}</b><small>{v.owner_name||v.owner_id||'No owner'} · {v.phone||v.owner_phone||'No phone'}</small><small>{v.slug} · {v.latitude!=null&&v.longitude!=null?'Map pin set':'Map pin required'}</small></span><span className={'seller-status '+v.status}>{v.status}</span><div className="seller-vendor-actions"><button type="button" className="secondary" disabled={busy} onClick={()=>{setVendorForm({id:v.id,owner_id:v.owner_id||'',owner_email:v.owner_email||'',owner_user_id:'',name:v.name||'',phone:v.phone||'',address:v.address||'',description:v.description||'',latitude:v.latitude==null?'':String(v.latitude),longitude:v.longitude==null?'':String(v.longitude),status:v.status||'pending'});document.querySelector('.admin-vendor-create')?.scrollIntoView({behavior:'smooth',block:'start'})}}>Set map pin</button>{['pending','approved','rejected','suspended'].map(st=><button key={st} className={v.status===st?'primary':'secondary'} disabled={busy||v.status===st} onClick={()=>updateVendorStatus(v,st)}>{st[0].toUpperCase()+st.slice(1)}</button>)}<button type="button" className="secondary" disabled={busy} onClick={()=>deleteVendor(v)}><FiTrash2 size={15}/><span>Delete vendor</span></button></div></article>)}
   </div>}
   {drawer==='manage'&&<form className="drawer-body form" onSubmit={saveProduct}><p>{productForm.id?'Update this product in your approved store.':'Add a product to your approved store.'}</p>
    <label>Product name<input required value={productForm.name} onChange={e=>setProductForm({...productForm,name:e.target.value})}/></label>
    <label>Short description<textarea rows="3" maxLength="4000" value={productForm.description} onChange={e=>setProductForm({...productForm,description:e.target.value})}/></label>
    <label>Additional product details<textarea rows="5" maxLength="12000" value={productForm.additional_description} onChange={e=>setProductForm({...productForm,additional_description:e.target.value})} placeholder="Fabric, fit, care instructions, material, occasion and other details"/></label>
    {profile?.role==='admin'?<label>Store<select required value={productForm.vendor_id} onChange={e=>setProductForm({...productForm,vendor_id:e.target.value})}><option value="">Choose approved store</option>{(sellerDashboard?.stores||[]).filter(s=>s.status==='approved').map(store=><option key={store.id} value={store.id}>{store.name}</option>)}</select></label>:<div className="seller-store-note">Store: <b>{sellerDashboard?.stores?.find(s=>s.id===productForm.vendor_id)?.name||sellerDashboard?.stores?.[0]?.name||'Your approved store'}</b><small>The server assigns products to your own approved store.</small></div>}
    <label>Category<select required value={productForm.category_id} onChange={e=>setProductForm({...productForm,category_id:e.target.value})}><option value="">Choose category</option>{categories.filter(c=>c.slug!=='all').map(c=><option key={c.id} value={c.id}>{c.parent_name?'↳ '+c.parent_name+' / ':''}{c.name}</option>)}</select><small>Choose the most specific category that matches this product.</small></label>
    <label>Sizes (comma-separated)<input value={productForm.sizes} onChange={e=>setProductForm({...productForm,sizes:e.target.value})} placeholder="S,M,L,XL"/></label><label>Size prices (₹, comma-separated)<input value={productForm.size_prices} onChange={e=>setProductForm({...productForm,size_prices:e.target.value})} placeholder="Leave blank for same base price"/><small>Prices match the size indexes in order. Example sizes S,M,L,XL and prices 299,329,359,399. Enter one price to apply it to every size; leave blank to use the base price for all sizes.</small></label>
    <div className="form-two"><label>Price (₹)<input required type="number" min="0" step="0.01" value={productForm.price} onChange={e=>setProductForm({...productForm,price:e.target.value})}/></label><label>Compare price<input type="number" min="0" step="0.01" value={productForm.compare_at_price} onChange={e=>setProductForm({...productForm,compare_at_price:e.target.value})}/></label></div>
    <label>Main product image (Cloudinary)<input type="file" accept="image/*" onChange={e=>uploadImage(e.target.files?.[0])}/></label>{productForm.image_url&&<img className="upload-preview" src={productForm.image_url} alt="Uploaded main product preview"/>}
     <label>Additional product images (up to 8)<input type="file" accept="image/*" multiple onChange={e=>{uploadGalleryImages(e.target.files);e.target.value=''}}/></label>
     {productForm.extra_images.length>0&&<div className="product-gallery-editor">{productForm.extra_images.map((image,index)=><div key={image.image_public_id||image.image_url}><img src={image.image_url} alt={image.alt_text||'Additional product image'}/><button type="button" className="secondary" disabled={busy} onClick={()=>setProductForm(p=>({...p,extra_images:p.extra_images.filter((_,i)=>i!==index)}))}><FiX size={13}/> Remove</button></div>)}</div>}
    <label>Sizes (comma separated)<input value={productForm.sizes} onChange={e=>setProductForm({...productForm,sizes:e.target.value})}/></label><label>Colours (comma separated)<input value={productForm.colors} onChange={e=>setProductForm({...productForm,colors:e.target.value})}/></label>
    <label>Stock quantity<input required type="number" min="0" value={productForm.stock_quantity} onChange={e=>setProductForm({...productForm,stock_quantity:e.target.value})}/></label>
    <button className="primary full" disabled={busy}>{busy?'Saving…':(productForm.id?'Update product':'Save product')}</button><button type="button" className="secondary full" onClick={()=>setDrawer('seller-dashboard')}>Cancel</button></form>}
  </aside></div>}
  {selected&&<div className="modal-backdrop product-detail-backdrop" onMouseDown={e=>e.target===e.currentTarget&&setSelected(null)}><section className="modal product-detail-modal" aria-label={selected.name+' product details'}><button className="icon close product-detail-close" aria-label="Close product details" onClick={()=>setSelected(null)}><FiX/></button><div className="product-detail-media"><div className="product-detail-main-image">{selectedHeroImage?<img src={selectedHeroImage.image_url} alt={selectedHeroImage.alt_text||selected.name} onError={e=>{e.currentTarget.style.display='none';e.currentTarget.parentElement.classList.add('image-failed')}}/>:<span className="placeholder">BF</span>}{detailLoading&&<span className="product-detail-loading">Loading details…</span>}</div>{selectedImages.length>1&&<div className="product-detail-thumbnails" aria-label="More product images">{selectedImages.map((image,index)=><button type="button" key={image.id||image.image_public_id||image.image_url||index} className={index===selectedImageIndex?'active':''} onClick={()=>setSelectedImageIndex(index)} aria-label={'View product image '+(index+1)}><img src={image.image_url} alt={image.alt_text||selected.name+' image '+(index+1)}/></button>)}</div>}</div><div className="modal-info product-detail-info"><div className="eyebrow muted">{selected.category_name||'CURATED STYLE'}</div><h2>{selected.name}</h2><h3>{money(priceForSize(selected,size))} {selected.compare_at_price&&Number(selected.compare_at_price)>priceForSize(selected,size)&&<del>{money(selected.compare_at_price)}</del>}</h3><p className="product-short-description">{selected.description||'A thoughtfully selected piece for your wardrobe.'}</p>{selected.additional_description&&<section className="product-additional-description"><h3>Product details</h3><p>{selected.additional_description}</p></section>}{selected.sizes?.length>0&&<div className="options"><b>Choose size</b><div>{selected.sizes.map(s=><button className={size===s?'selected':''} key={s} onClick={()=>setSize(s)}>{s}</button>)}</div></div>}{selected.colors?.length>0&&<div className="options"><b>Choose colour</b><div>{selected.colors.map(c=><button className={color===c?'selected':''} key={c} onClick={()=>setColor(c)}>{c}</button>)}</div></div>}<div className="product-detail-buy"><button className="primary full" disabled={busy||detailLoading||Number(selected.stock_quantity??selected.stock??0)<1} onClick={()=>add(selected,size,color)}><FiShoppingBag size={16}/> {Number(selected.stock_quantity??selected.stock??0)<1?'Currently unavailable':`Add to bag — ${money(priceForSize(selected,size))}`}</button><small className="delivery"><FiTruck size={14}/> Local delivery · Cash on delivery</small></div></div></section></div>}
  {toast&&<div className="toast"><FiCheck size={16}/>{toast}</div>}
 </div>
}
