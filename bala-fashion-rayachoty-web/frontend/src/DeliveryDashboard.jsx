import { useCallback, useEffect, useState } from 'react'
import { ArrowRight, Check, MapPin, Package, RefreshCw, Truck, UserPlus } from 'lucide-react'
import { api } from './api'

const money = value => `₹${Number(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`

export function DeliveryManagement({ session, orders = [], busy, onRefresh, notify, authUsers = [] }) {
  const [staff, setStaff] = useState([])
  const [userId, setUserId] = useState('')
  const [userSearch, setUserSearch] = useState('')
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [assignments, setAssignments] = useState({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const loadStaff = useCallback(async () => {
    if (!session?.access_token) return
    try {
      const data = await api('/delivery/staff/', { token: session.access_token })
      setStaff(data.results || [])
      setError('')
    } catch (err) {
      setError(err.message || 'Could not load delivery team. Please try again.')
    }
  }, [session?.access_token])

  useEffect(() => { loadStaff() }, [loadStaff])

  async function updateStaff(person, changes) {
    if (!session?.access_token || saving) return
    setSaving(true)
    try {
      await api('/delivery/staff/', { method:'PATCH', token:session.access_token, body:JSON.stringify({id:person.id,...changes}) })
      await loadStaff()
      notify('Delivery staff status updated')
    } catch (err) { notify(err.message || 'Could not update delivery staff') }
    finally { setSaving(false) }
  }

  async function addStaff(event) {
    event.preventDefault()
    if (!session?.access_token || saving) return
    setSaving(true)
    try {
      await api('/delivery/staff/', {
        method: 'POST', token: session.access_token,
        body: JSON.stringify({ user_id: userId, full_name: fullName.trim(), phone: phone.trim() }),
      })
      setUserId(''); setUserSearch(''); setFullName(''); setPhone('')
      await loadStaff()
      notify('Delivery account created. The delivery person can now choose Online or Offline.')
    } catch (err) {
      notify(err.message || 'Could not enable delivery staff.')
    } finally { setSaving(false) }
  }

  async function removeStaff(person) {
    if (!session?.access_token || saving) return
    if (!window.confirm('Remove delivery access for ' + (person.email || person.full_name || person.id) + '? Their account will return to customer role and active orders will be unassigned.')) return
    setSaving(true)
    try {
      await api('/delivery/staff/', { method: 'DELETE', token: session.access_token, body: JSON.stringify({ id: person.id }) })
      await Promise.all([loadStaff(), onRefresh?.()])
      notify('Delivery person removed')
    } catch (err) {
      notify(err.message || 'Could not remove delivery staff.')
    } finally { setSaving(false) }
  }
  async function assign(order) {
    const deliveryBoyId = assignments[order.id] || order.assigned_delivery_boy_id || ''
    if (!deliveryBoyId) return notify('Choose a delivery person first.')
    setSaving(true)
    try {
      await api('/delivery/assign/', {
        method: 'PATCH', token: session.access_token,
        body: JSON.stringify({ order_id: order.id, delivery_boy_id: deliveryBoyId }),
      })
      notify(`Delivery person assigned to ${order.order_number}`)
      await Promise.all([loadStaff(), onRefresh?.()])
    } catch (err) {
      notify(err.message || 'Could not assign delivery person.')
    } finally { setSaving(false) }
  }

  return <div className="drawer-body seller-dashboard">
    <div className="seller-dashboard-head">
      <div><b>Delivery staff</b><small>View delivery availability and assign orders to people who are online.</small></div>
      <button className="secondary" onClick={loadStaff}><RefreshCw size={14}/> Refresh</button>
    </div>
    <form className="form admin-vendor-create" onSubmit={addStaff}>
      <h3><UserPlus size={17}/> Add delivery person</h3>
      <label>Find an account<input type="search" value={userSearch} onChange={event=>setUserSearch(event.target.value)} placeholder="Search registered email…" autoComplete="off"/></label>
      <label>Delivery staff account<select required value={userId} onChange={event=>setUserId(event.target.value)}>
        <option value="">Choose an existing customer account</option>
        {authUsers.filter(person=>person.email&&(!person.role||person.role==='customer')&&person.email.toLowerCase().includes(userSearch.trim().toLowerCase())).map(person=><option key={person.id} value={person.id}>{person.email}{person.full_name?' — '+person.full_name:''}</option>)}
      </select></label>
      <small>Choose an existing customer account.</small>
      <label>Display name (optional)<input value={fullName} onChange={event => setFullName(event.target.value)} maxLength={120}/></label>
      <label>Phone (optional)<input value={phone} onChange={event => setPhone(event.target.value)} maxLength={30} inputMode="tel"/></label>
      <button className="primary full" disabled={saving}>{saving ? 'Saving…' : 'Enable delivery account'}</button>
    </form>
    {error && <div className="warning">{error}</div>}
    <section className="seller-dashboard-section">
      <h3>Authorized delivery people ({staff.length})</h3>
      {!staff.length ? <p className="seller-empty">No delivery people added yet.</p> : staff.map(person =>
        <article className="seller-store-row" key={person.id}>
          <span><b>{person.full_name || 'Delivery person'}</b><small>{person.email || 'No email'} · {person.phone || 'No phone'}</small><small>{person.id}</small></span>
          <span className={'seller-status '+(person.availability_status==='available'?'approved':'suspended')}>{person.availability_status==='available'?'Online':'Offline'}</span>
          {person.last_location_at && <small>Location updated {new Date(person.last_location_at).toLocaleString('en-IN')} {person.latitude != null && person.longitude != null ? '· '+Number(person.latitude).toFixed(4)+', '+Number(person.longitude).toFixed(4) : ''}</small>}
          <span className="seller-product-actions"><button type="button" className="secondary" disabled={saving || busy} onClick={() => removeStaff(person)}>Remove role</button></span>
        </article>
      )}
    </section>
    <section className="seller-dashboard-section">
      <h3>Assign orders</h3>
      <p className="muted">Assign a packed order to an available delivery person.</p>
      {!orders.filter(order => ['packed', 'out_for_delivery'].includes(order.status)).length
        ? <p className="seller-empty">No orders ready to assign.</p>
        : orders.filter(order => ['packed', 'out_for_delivery'].includes(order.status)).map(order =>
          <article className="seller-order-row" key={order.id}>
            <span>
              <b>{order.order_number}</b>
              <small>{order.status.replaceAll('_', ' ')} · {order.assigned_delivery_boy_id ? 'Assigned' : 'Unassigned'}</small>
            </span>
            <span className="delivery-assignment-controls">
              <select aria-label={`Delivery person for ${order.order_number}`} value={assignments[order.id] ?? order.assigned_delivery_boy_id ?? ''} onChange={event => setAssignments(current => ({ ...current, [order.id]: event.target.value }))}>
                <option value="">Choose online delivery person</option>
                {staff.filter(person=>person.is_active && person.availability_status==='available').sort((a,b)=> {
                  const destination=order.delivery_coordinates||{}
                  const distance=person=> {
                    if(destination.latitude==null||destination.longitude==null||person.latitude==null||person.longitude==null) return Number.POSITIVE_INFINITY
                    const rad=value=>Number(value)*Math.PI/180
                    const dLat=rad(Number(destination.latitude)-Number(person.latitude))
                    const dLon=rad(Number(destination.longitude)-Number(person.longitude))
                    const x=Math.sin(dLat/2)**2+Math.cos(rad(person.latitude))*Math.cos(rad(destination.latitude))*Math.sin(dLon/2)**2
                    return 6371*2*Math.atan2(Math.sqrt(x),Math.sqrt(1-x))
                  }
                  const da=distance(a), db=distance(b)
                  if(da!==db) return da-db
                  return String(a.full_name||'').localeCompare(String(b.full_name||''))
                }).map(person => <option key={person.id} value={person.id}>{person.full_name || person.phone || person.id.slice(0, 8)}{person.latitude!=null&&person.longitude!=null&&order.delivery_coordinates?.latitude!=null&&order.delivery_coordinates?.longitude!=null?' · '+(function(){const rad=x=>Number(x)*Math.PI/180;const dl=rad(Number(order.delivery_coordinates.latitude)-Number(person.latitude));const dn=rad(Number(order.delivery_coordinates.longitude)-Number(person.longitude));const h=Math.sin(dl/2)**2+Math.cos(rad(person.latitude))*Math.cos(rad(Number(order.delivery_coordinates.latitude)))*Math.sin(dn/2)**2;return (6371*2*Math.atan2(Math.sqrt(h),Math.sqrt(1-h))).toFixed(1)+' km'}()):''}</option>)}
              </select>
              <button className="secondary" disabled={saving || !staff.some(person=>person.is_active&&person.availability_status==='available')} onClick={() => assign(order)}>Assign <ArrowRight size={14}/></button>
            </span>
          </article>
        )}
    </section>
  </div>
}

export function DeliveryDashboard({ session, notify, onSignOut }) {
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [busyOrder, setBusyOrder] = useState('')
  const [error, setError] = useState('')
  const [otpInputs, setOtpInputs] = useState({})
  const [isActive, setIsActive] = useState(false)
  const [availabilityStatus, setAvailabilityStatus] = useState('offline')
  const [availabilityBusy, setAvailabilityBusy] = useState(false)

  const loadOrders = useCallback(async () => {
    if (!session?.access_token) return
    setLoading(true)
    try {
      const data = await api('/delivery/orders/', { token: session.access_token })
      setOrders(data.results || [])
      setIsActive(Boolean(data.is_active))
      setAvailabilityStatus(data.availability_status || 'offline')
      if (data.notifications?.length) data.notifications.forEach(item => notify(item.message || 'A delivery order was assigned to you.'))
      setError('')
    } catch (err) {
      setError(err.message || 'Could not load your deliveries. Please try again.')
    } finally { setLoading(false) }
  }, [session?.access_token])

  useEffect(() => { loadOrders() }, [loadOrders])
  useEffect(() => {
    const timer = window.setInterval(loadOrders, 30000)
    return () => window.clearInterval(timer)
  }, [loadOrders])

  useEffect(() => {
    if (!session?.access_token || !isActive || availabilityStatus !== 'available' || !navigator.geolocation) return
    let active = true
    const shareLocation = () => navigator.geolocation.getCurrentPosition(async position => {
      if (!active) return
      try {
        await api('/delivery/location/', {method:'POST',token:session.access_token,body:JSON.stringify({
          latitude:position.coords.latitude, longitude:position.coords.longitude, availability_status:'available'
        })})
      } catch (err) { if (active) setError(err.message || 'Could not share delivery location.') }
    }, () => { if (active) setError('Allow location access to share your delivery location while available.') }, {enableHighAccuracy:true, maximumAge:60000, timeout:12000})
    shareLocation()
    const timer = window.setInterval(shareLocation, 120000)
    return () => { active=false; window.clearInterval(timer) }
  }, [session?.access_token, isActive, availabilityStatus])

  async function toggleAvailability() {
    if (!session?.access_token || availabilityBusy || !isActive) return
    const next = availabilityStatus === 'available' ? 'offline' : 'available'
    setAvailabilityBusy(true)
    try {
      const result = await api('/delivery/availability/', {
        method:'PATCH', token:session.access_token,
        body:JSON.stringify({availability_status:next}),
      })
      setAvailabilityStatus(result.availability_status || next)
      notify(result.detail || (next === 'available' ? 'You are now available for deliveries.' : 'You are now offline.'))
      await loadOrders()
    } catch (err) {
      notify(err.message || 'Could not change delivery availability.')
    } finally { setAvailabilityBusy(false) }
  }

  async function updatePreparationStatus(order, status) {
    const label = status === 'confirmed' ? 'confirm' : status === 'packed' ? 'mark packed' : 'cancel'
    if (!window.confirm('Are you sure you want to ' + label + ' ' + order.order_number + '?')) return
    setBusyOrder(order.id)
    try {
      await api('/delivery/orders/', { method:'PATCH', token:session.access_token, body:JSON.stringify({order_id:order.id,status}) })
      notify(order.order_number + ': ' + status.replaceAll('_',' ') + '.')
      await loadOrders()
    } catch (err) {
      notify(err.message || 'Could not update order status.')
    } finally { setBusyOrder('') }
  }

  async function startDelivery(order) {
    if (!window.confirm(`Mark ${order.order_number} out for delivery and email the customer a verification code?`)) return
    setBusyOrder(order.id)
    try {
      await api('/delivery/verify/', { method:'POST', token:session.access_token, body:JSON.stringify({ order_id:order.id, action:'start' }) })
      notify(`OTP emailed to the customer's registered email for ${order.order_number}.`)
      await loadOrders()
    } catch (err) {
      notify(err.message || 'Could not start delivery.')
    } finally { setBusyOrder('') }
  }

  async function sendMailjetDeliveryCode(order) {
    if (!window.confirm(`Send a delivery verification OTP for ${order.order_number} using Mailjet instead of SMTP?`)) return
    setBusyOrder(order.id)
    try {
      await api('/delivery/verify/', { method:'POST', token:session.access_token, body:JSON.stringify({ order_id:order.id, action:'mailjet' }) })
      notify(`Mailjet sent the verification OTP to the customer's registered email for ${order.order_number}.`)
      await loadOrders()
    } catch (err) {
      notify(err.message || 'Could not send the OTP through Mailjet.')
      await loadOrders()
    } finally { setBusyOrder('') }
  }

  async function resendDeliveryCode(order) {
    setBusyOrder(order.id)
    try {
      await api('/delivery/verify/', { method:'POST', token:session.access_token, body:JSON.stringify({ order_id:order.id, action:'resend' }) })
      notify(`A new OTP was emailed for ${order.order_number}.`)
    } catch (err) {
      notify(err.message || 'Could not resend delivery OTP.')
    } finally { setBusyOrder('') }
  }

  async function verifyDelivery(order) {
    const otp = String(otpInputs[order.id] || '').trim()
    if (!/^\d{6}$/.test(otp)) return notify('Enter the six-digit customer email OTP.')
    if (!window.confirm(`Confirm the customer received ${order.order_number} and supplied the email OTP?`)) return
    setBusyOrder(order.id)
    try {
      await api('/delivery/verify/', { method:'POST', token:session.access_token, body:JSON.stringify({ order_id:order.id, action:'verify', otp }) })
      setOtpInputs(current => ({ ...current, [order.id]:'' }))
      notify(`${order.order_number} delivered after OTP verification.`)
      await loadOrders()
    } catch (err) {
      notify(err.message || 'Could not verify delivery OTP.')
    } finally { setBusyOrder('') }
  }

  return <div className="drawer-body seller-dashboard">
    <div className="seller-dashboard-head">
      <div><b><Truck size={17}/> Delivery dashboard</b><small>Only orders assigned to your account are shown.</small></div>
      <div className="seller-dashboard-head-actions">
        <span className={'seller-status '+(availabilityStatus==='available'?'approved':'suspended')}>{availabilityStatus==='available'?'Online':'Offline'}</span>
        <button className={availabilityStatus==='available'?'secondary':'primary'} onClick={toggleAvailability} disabled={availabilityBusy}>{availabilityBusy?'Saving…':availabilityStatus==='available'?'Go offline':'Go online'}</button>
        <button className="secondary" onClick={loadOrders} disabled={loading}><RefreshCw size={14}/> Refresh</button>
        <button className="secondary" onClick={onSignOut}>Sign out</button>
      </div>
    </div>
    <div className="seller-stat-grid">
      <div><b>{orders.length}</b><small>Assigned orders</small></div>
      <div><b>{orders.filter(order => order.status === 'out_for_delivery').length}</b><small>On the way</small></div>
      <div><b>{orders.filter(order => order.status === 'delivered').length}</b><small>Delivered</small></div>
    </div>
    {error && <div className="warning">{error}<button className="secondary" onClick={loadOrders}>Retry</button></div>}
    {loading ? <p>Loading assigned deliveries…</p> : !orders.length ? <div className="empty"><Package size={28}/><h3>No assigned deliveries</h3><p>Ask the administrator to assign an order to your account.</p></div> :
      orders.map(order => {
        const address = order.address_snapshot || {}
        const canConfirm = order.status === 'placed'
        const canPack = order.status === 'confirmed'
        const canStart = order.status === 'packed'
        const canDeliver = order.status === 'out_for_delivery'
        const destination = [address.line1, address.line2, address.landmark, address.city || 'Rayachoty'].filter(Boolean).join(', ')
        const navigation = address.latitude != null && address.longitude != null
          ? `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(address.latitude + ',' + address.longitude)}&travelmode=driving`
          : ''
        return <article className="seller-order-row delivery-order-card" key={order.id}>
          <span className="delivery-order-details">
            <b>{order.order_number}</b>
            <small>Status: {order.status.replaceAll('_', ' ')}</small>
            <b>Vendor / pickup</b>
            <small>{order.vendor_name || 'Vendor name unavailable'}</small>
            <small>{order.vendor_address || 'Vendor address not provided'}</small>
            {order.vendor_phone && <small>Vendor phone: <a href={`tel:${order.vendor_phone}`}>{order.vendor_phone}</a></small>}
            <b>Customer / drop-off</b>
            <small>{address.recipient_name || 'Customer'} · {address.phone || 'No phone'}</small>
            {order.customer_email && <small>Email: <a href={`mailto:${order.customer_email}`}>{order.customer_email}</a></small>}
            <small>{destination || 'Address not provided'}{address.state ? `, ${address.state}` : ''}{address.postal_code ? ` ${address.postal_code}` : ''}</small>
            {navigation && <a href={navigation} target="_blank" rel="noreferrer"><MapPin size={14}/> Navigate to customer</a>}
            <b>Items ({(order.items || []).length})</b>
            {(order.items || []).map((item,index) => <small key={`${order.id}-item-${index}`}>{item.quantity} × {item.product_name}{item.size ? ` · Size ${item.size}` : ''}{item.color ? ` · ${item.color}` : ''} · {money(item.line_total)}</small>)}
            <small>Subtotal: {money(order.subtotal)} · Delivery: {money(order.delivery_fee)}</small>
            <small>Payment: {String(order.payment_method || 'cod').toUpperCase()} · {order.payment_status === 'paid' ? 'Paid' : 'Payment pending'} · Total {money(order.total)}</small>
            {order.notes && <small>Order instructions: {order.notes}</small>}
          </span>
          <span className="delivery-order-actions">
            {canConfirm ? <span className="delivery-otp-controls"><button className="primary" disabled={busyOrder === order.id} onClick={() => updatePreparationStatus(order,'confirmed')}>Confirm order</button><button className="secondary" disabled={busyOrder === order.id} onClick={() => updatePreparationStatus(order,'cancelled')}>Reject order</button></span> : canPack ? <span className="delivery-otp-controls"><button className="primary" disabled={busyOrder === order.id} onClick={() => updatePreparationStatus(order,'packed')}><Package size={15}/> Mark packed</button></span> : canStart ? <span className="delivery-otp-controls"><button className="primary" disabled={busyOrder === order.id} onClick={() => startDelivery(order)}><Truck size={15}/>{busyOrder === order.id ? 'Sending OTP…' : 'Out for delivery (SMTP)'}</button><button className="secondary" disabled={busyOrder === order.id} onClick={() => sendMailjetDeliveryCode(order)}>Start & send OTP via Mailjet</button></span> : canDeliver ? <span className="delivery-otp-controls"><label>Customer email OTP<input aria-label={`Delivery OTP for ${order.order_number}`} inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={otpInputs[order.id] || ''} onChange={event=>setOtpInputs(current=>({...current,[order.id]:event.target.value.replace(/\\D/g,'').slice(0,6)}))} placeholder="6-digit code"/></label><button className="secondary" disabled={busyOrder === order.id} onClick={() => resendDeliveryCode(order)}>Resend OTP (SMTP)</button><button className="secondary" disabled={busyOrder === order.id} onClick={() => sendMailjetDeliveryCode(order)}>Send OTP via Mailjet</button><button className="primary" disabled={busyOrder === order.id || String(otpInputs[order.id] || '').length !== 6} onClick={() => verifyDelivery(order)}><Check size={15}/>{busyOrder === order.id ? 'Verifying…' : 'Verify & deliver'}</button></span> : <span className="seller-status approved">{order.status.replaceAll('_', ' ')}</span>}
          </span>
        </article>
      })
    }
  </div>
}
