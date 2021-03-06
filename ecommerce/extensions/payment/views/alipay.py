""" Views for interacting with the payment processor. """
from __future__ import unicode_literals

import logging
import os
from cStringIO import StringIO

from django.core.exceptions import MultipleObjectsReturned
from django.core.management import call_command
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import View
from oscar.apps.partner import strategy
from oscar.apps.payment.exceptions import PaymentError
from oscar.core.loading import get_class, get_model

from ecommerce.extensions.checkout.mixins import EdxOrderPlacementMixin
from ecommerce.extensions.checkout.utils import get_receipt_page_url
from ecommerce.extensions.payment.processors.alipay import Alipay

from django.http import HttpResponse

from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt


logger = logging.getLogger(__name__)

Applicator = get_class('offer.utils', 'Applicator')
Basket = get_model('basket', 'Basket')
BillingAddress = get_model('order', 'BillingAddress')
Country = get_model('address', 'Country')
NoShippingRequired = get_class('shipping.methods', 'NoShippingRequired')
OrderNumberGenerator = get_class('order.utils', 'OrderNumberGenerator')
OrderTotalCalculator = get_class('checkout.calculators', 'OrderTotalCalculator')
PaymentProcessorResponse = get_model('payment', 'PaymentProcessorResponse')


class AlipayPaymentExecutionView(EdxOrderPlacementMixin, View):
    """Execute an approved Alipay payment and place an order for paid products as appropriate."""

    @property
    def payment_processor(self):
        return Alipay(self.request.site)

    # Disable atomicity for the view. Otherwise, we'd be unable to commit to the database
    # until the request had concluded; Django will refuse to commit when an atomic() block
    # is active, since that would break atomicity. Without an order present in the database
    # at the time fulfillment is attempted, asynchronous order fulfillment tasks will fail.
    @method_decorator(transaction.non_atomic_requests)
    def dispatch(self, request, *args, **kwargs):
        return super(AlipayPaymentExecutionView, self).dispatch(request, *args, **kwargs)

    def _get_basket(self, payment_id):
        """
        Retrieve a basket using a payment ID.

        Arguments:
            payment_id: payment_id received from Alipay.

        Returns:
            It will return related basket or log exception and return None if
            duplicate payment_id received or any other exception occurred.

        """
        try:
            basket = PaymentProcessorResponse.objects.get(
                processor_name=self.payment_processor.NAME,
                transaction_id=payment_id
            ).basket
            basket.strategy = strategy.Default()
            Applicator().apply(basket, basket.owner, self.request)
            return basket
        except MultipleObjectsReturned:
            logger.warning(u"Duplicate payment ID [%s] received from Alipay.", payment_id)
            return None
        except Exception:  # pylint: disable=broad-except
            logger.exception(u"Unexpected error during basket retrieval while executing Alipay payment.")
            return None

    def get(self, request):
        """Handle an incoming user returned to us by Alipay after approving payment."""
        payment_id = request.GET.get('out_trade_no')
        logger.info(u"Payment [%s] approved", payment_id)

        alipay_response = request.GET.dict()
        basket = self._get_basket(payment_id)

        if not basket:
            return redirect(self.payment_processor.error_url)

        receipt_url = get_receipt_page_url(
            order_number=basket.order_number,
            site_configuration=basket.site.siteconfiguration
        )

        try:
            shipping_method = NoShippingRequired()
            shipping_charge = shipping_method.calculate(basket)
            order_total = OrderTotalCalculator().calculate(basket, shipping_charge)

            user = basket.owner
            # Given a basket, order number generation is idempotent. Although we've already
            # generated this order number once before, it's faster to generate it again
            # than to retrieve an invoice number from Alipay.
            order_number = basket.order_number

            self.handle_order_placement(
                order_number=order_number,
                user=user,
                basket=basket,
                shipping_address=None,
                shipping_method=shipping_method,
                shipping_charge=shipping_charge,
                billing_address=None,
                order_total=order_total,
                request=request
            )

            return redirect(receipt_url)
        except:  # pylint: disable=bare-except
            logger.exception(self.order_placement_failure_msg, basket.id)
            return redirect(receipt_url)


class AlipayProfileAdminView(View):
    ACTIONS = ('list', 'create', 'show', 'update', 'delete', 'enable', 'disable')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise Http404

        return super(AlipayProfileAdminView, self).dispatch(request, *args, **kwargs)

    def get(self, request, *_args, **_kwargs):

        # Capture all output and logging
        out = StringIO()
        err = StringIO()
        log = StringIO()

        log_handler = logging.StreamHandler(log)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        log_handler.setFormatter(formatter)
        logger.addHandler(log_handler)

        action = request.GET.get('action')
        if action not in self.ACTIONS:
            return HttpResponseBadRequest("Invalid action.")
        profile_id = request.GET.get('id', '')
        json_str = request.GET.get('json', '')

        command_params = [action]
        if action in ('show', 'update', 'delete', 'enable', 'disable'):
            command_params.append(profile_id.strip())
        if action in ('create', 'update'):
            command_params.append(json_str.strip())

        logger.info("user %s is managing alipay profiles: %s", request.user.username, command_params)

        success = False
        try:
            call_command('alipay_profile', *command_params,
                         settings=os.environ['DJANGO_SETTINGS_MODULE'], stdout=out, stderr=err)
            success = True
        except:  # pylint: disable=bare-except
            # we still want to present the output whether or not the command succeeded.
            pass

        # Format the output for display
        output = u'STDOUT\n{out}\n\nSTDERR\n{err}\n\nLOG\n{log}'.format(out=out.getvalue(), err=err.getvalue(),
                                                                        log=log.getvalue())

        # Remove the log capture handler
        logger.removeHandler(log_handler)

        return HttpResponse(output, content_type='text/plain', status=200 if success else 500)


@require_POST
@csrf_exempt
def ptn(request, item_check_callable=None):
    """
    Recevied notify from alipay by POST method
    """
    flag = None
    ptn_obj = None
    post_data = request.POST.copy()
        # cleanup data
    data = {}
    for k,v in post_data.items():
        data[k] = v
        # valid data
    form = None #AliPayPTNForm(data)
    if form.is_valid():
        try:
            ptn_obj = form.save(commit=False)
        except Exception as e:
            flag = 'Exception while processing: %s'% e

    else:
        flag = 'Invalid: %s'% form.errors
    if ptn_obj is None:
        ptn_obj = None#AliPayPTN()

       #Set query params and sender's IP address
    ptn_obj.initialize(request)

    if flag is not None:
        #We save errors in the flag field
        ptn_obj.set_flag(flag)
    else:
        ptn_obj.verify(item_check_callable)
    ptn_obj.save()
    return HttpResponse('success')
