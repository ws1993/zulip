class kandra::profile::chat_zulip_org inherits kandra::profile::base {
  include zulip::profile::standalone
  include zulip::postfix_localmail
  include zulip::hooks::sentry

  include kandra::app_frontend_monitoring
  include kandra::prometheus::redis
  include kandra::prometheus::postgresql
  kandra::firewall_allow { 'smokescreen_metrics': port => '9810' }
  kandra::firewall_allow { 'http': }
  kandra::firewall_allow { 'https': }
  kandra::firewall_allow { 'smtp': }

  Kandra::User_Dotfiles['root'] {
    keys => false,
  }
  Kandra::User_Dotfiles['zulip'] {
    keys => false,
  }
}
