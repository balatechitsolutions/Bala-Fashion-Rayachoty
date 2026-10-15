import { FiChevronRight } from 'react-icons/fi'

const STATUS_CLASS = {
  pending: 'is-pending',
  confirmed: 'is-confirmed',
  packed: 'is-packed',
  out_for_delivery: 'is-out-for-delivery',
  delivered: 'is-delivered',
  cancelled: 'is-cancelled',
  canceled: 'is-cancelled',
}

const formatStatus = value => String(value || 'unknown').trim().replaceAll('_', ' ')
const getStatusClass = value => STATUS_CLASS[String(value || '').trim().toLowerCase()] || 'is-unknown'

export default function DeliveryOrderSummary({ order, expanded, onToggle }) {
  const orderNumber = String(order?.order_number || 'Order')
  const status = formatStatus(order?.status)
  const statusClass = getStatusClass(order?.status)

  return (
    <button
      type="button"
      className="delivery-order-summary"
      aria-expanded={Boolean(expanded)}
      aria-label={orderNumber + ', status ' + status + '. ' + (expanded ? 'Collapse' : 'Expand') + ' order details'}
      onClick={onToggle}
    >
      <span className="delivery-order-summary-text">
        <b className="delivery-order-number">{orderNumber}</b>
        <small className={'delivery-order-status ' + statusClass}>
          <span className="delivery-order-status-label">Status</span>
          <span>{status}</span>
        </small>
      </span>
      <span className={'delivery-order-chevron-wrap' + (expanded ? ' expanded' : '')} aria-hidden="true">
        <FiChevronRight size={19} className="delivery-order-chevron" />
      </span>
    </button>
  )
}
