import { useCallback, useEffect, useState } from 'react'
import { ArrowRight, Check, MapPin, Package, RefreshCw, Truck, UserPlus } from 'lucide-react'
import { api } from './api'

const money = value => `₹${Number(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}'

export function DeliveryManagement({ session, orders = [], busy, onRefresh, notify }) {
  const [staff, setStaff] = useState([])
  const [userId, setUserId] = useState('')
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
      setError(err.message || 'Could not load delivery staff.')
    }
  }, [session?.access_token])

  useEffect(() => { loadStaff() }, [loadStaff])

  async function addStaff(event) {
    event.preventDefault()
    if (!session?.access_token || saving) return
    setSaving(true)
    try {
      await api('/delivery/staff/', {
        method: 'POST', token: session.access_token,
        body: JSON.stringify({ user_id: userId.trim(), full_name: fullName.trim(), phone: phone.trim() }),
      })
      setUserId(''); setFullName(''); setPhone('')
      await loadStaff()
      notify('Delivery-boy role enabled. The user can now sign in.')
    } catch (err) {
      notify(err.message || 'Could not enable delivery staff.')
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
      <div><b>Delivery staff</b><small>Authorize an existing Supabase user and assign local deliveries.</small></div>
      <button className="secondary" onClick={loadStaff}><RefreshCw size={14}/> Refresh</button>
    </div>
    <form className="form admin-vendor-create" onSubmit={addStaff}>
      <h3><UserPlus size={17}/> Authorize delivery person</h3>
      <label>Existing Supabase Auth user UUID
        <input required value={userId} onChange={event => setUserId(event.target.value.trimStart())} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" autoCapitalize="off" autoCorrect="off" spellCheck="false"/>
      </label>
      <small>Create the user first in Supabase → Authentication → Users. This action grants only the delivery_boy role.</small>
      <label>Display name (optional)<input value={fullName} onChange={event => setFullName(event.target.value)} maxLength={120}/></label>
      <label>Phone (optional)<input value={phone} onChange={event => setPhone(event.target.value)} maxLength={30} inputMode="tel"/></label>
      <button className="primary full" disabled={saving}>{saving ? 'Saving…' : 'Enable delivery account'}</button>
    </form>
    {error && <div className="warning">{error}</div>}
    <section className="seller-dashboard-section">
      <h3>Authorized delivery people ({staff.length})</h3>
      {!staff.length ? <p className="seller-empty">No delivery accounts yet.</p> : staff.map(person =>
        <article className="seller-store-row" key={person.id}>
          <span><b>{person.full_name || 'Delivery person'}</b><small>{person.phone || 'No phone'} · {person.id}</small></span>
          <span className="seller-status approved">Active</span>
        </article>
      )}
    </section>
    <section className="seller-dashboard-section">
      <h3>Assign orders</h3>
      <p className="muted">Orders must be packed or out for delivery before assignment.</p>
      {!orders.filter(order => ['packed', 'out_for_delivery'].includes(order.status)).length
        ? <p className="seller-empty">No orders ready for assignment.</p>
        : orders.filter(order => ['packed', 'out_for_delivery'].includes(order.status)).map(order =>
          <article className="seller-order-row" key={order.id}>
            <span>
              <b>{order.order_number}</b>
              <small>{order.vendor_name} · {order.status.replaceAll('_', ' ')}</small>
              {order.address_snapshot?.recipient_name && <small>{order.address_snapshot.recipient_name} · {order.address_snapshot.phone || ''}</small>}
            </span>
            <span className="delivery-assignment-controls">
              <select aria-label={`Delivery person for ${order.order_number}`} value={assignments[order.id] ?? order.assigned_delivery_boy_id ?? ''} onChange={event => setAssignments(current => ({ ...current, [order.id]: event.target.value }))}>
                <option value="">Choose delivery person</option>
                {staff.map(person => <option key={person.id} value={person.id}>{person.full_name || person.phone || person.id.slice(0, 8)}</option>)}
              </select>
              <button className="secondary" disabled={saving || !staff.length} onClick={() => assign(order)}>Assign <ArrowRight size={14}/></button>
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

  const loadOrders = useCallback(async () => {
    if (!session?.access_token) return
    setLoading(true)
    try {
      const data = await api('/delivery/orders/', { token: session.access_token })
      setOrders(data.results || [])
      setError('')
    } catch (err) {
      setError(err.message || 'Could not load your assigned deliveries.')
    } finally { setLoading(false) }
  }, [session?.access_token])

  useEffect(() => { loadOrders() }, [loadOrders])

  async function markDelivered(order) {
    if (!window.confirm(`Confirm that order ${order.order_number} has been delivered?`)) return
    setBusyOrder(order.id)
    try {
      await api('/delivery/orders/', {
        method: 'PATCH', token: session.access_token,
        body: JSON.stringify({ id: order.id }),
      })
      notify(`${order.order_number} marked delivered.`)
      await loadOrders()
    } catch (err) {
      notify(err.message || 'Could not mark order delivered.')
    } finally { setBusyOrder('') }
  }

  return <div className="drawer-body seller-dashboard">
    <div className="seller-dashboard-head">
      <div><b><Truck size={17}/> Delivery dashboard</b><small>Only orders assigned to your account are shown.</small></div>
      <div className="seller-dashboard-head-actions">
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
        const canDeliver = order.status === 'out_for_delivery'
        const destination = [address.line1, address.line2, address.landmark, address.city || 'Rayachoty'].filter(Boolean).join(', ')
        const navigation = address.latitude != null && address.longitude != null
          ? `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(address.latitude + ',' + address.longitude)}&travelmode=driving`
          : ''
        return <article className="seller-order-row delivery-order-card" key={order.id}>
          <span>
            <b>{order.order_number}</b>
            <small>{order.vendor_name} · {order.status.replaceAll('_', ' ')}</small>
            <small>{address.recipient_name || 'Customer'} · {address.phone || 'No phone'}</small>
            <small>{destination || 'Address not provided'}</small>
            {navigation && <a href={navigation} target="_blank" rel="noreferrer"><MapPin size={14}/> Navigate to customer</a>}
            <small>COD · {order.payment_status === 'paid' ? 'Marked paid' : 'Payment pending'} · {money(order.total)}</small>
          </span>
          <span className="delivery-order-actions">
            {canDeliver ? <button className="primary" disabled={busyOrder === order.id} onClick={() => markDelivered(order)}><Check size={15}/>{busyOrder === order.id ? 'Saving…' : 'Mark delivered'}</button> : <span className="seller-status approved">{order.status.replaceAll('_', ' ')}</span>}
          </span>
        </article>
      })
    }
  </div>
}
