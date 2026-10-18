# -*- mode: ruby -*-
require_relative 'config/topology'
require 'fileutils'
if File.exist?(File.join(__dir__, '.runtime', 'promoted')) &&
   %w[up reload provision].include?(ARGV[0])
  raise 'bdd2 was promoted. Keep bdd1 fenced; use scripts/ops.py rebuild --confirm-destroy-project-vms for lab failback.'
end
settings = Resultats.settings
topology = Resultats.inventory(settings)
runtime = File.join(__dir__, '.runtime')
FileUtils.mkdir_p(runtime, mode: 0700)
File.write(File.join(runtime, 'inventory.json'), JSON.pretty_generate(topology))
secret_keys = %w[DB_PASSWORD REPLICATION_PASSWORD REDIS_PASSWORD]
# Read-only commands still work before setup; provisioning rejects absent secrets.
secret_keys.each do |key|
  value = settings[key]
  raise "#{key} must be 32+ hexadecimal characters" if value && !value.match?(/\A[0-9a-f]{32,}\z/)
end
Vagrant.configure('2') do |config|
  config.vm.box = 'bento/ubuntu-24.04'
  config.vm.box_version = '202502.21.0'
  config.vm.boot_timeout = 600
  config.vm.synced_folder '.', '/vagrant', disabled: true
  topology[:nodes].each_with_index do |node, index|
    keys = case node[:role]
           when 'primary' then %w[DB_PASSWORD REPLICATION_PASSWORD]
           when 'replica' then %w[REPLICATION_PASSWORD]
           when 'app' then %w[DB_PASSWORD REDIS_PASSWORD]
           else %w[REDIS_PASSWORD]
           end
    path = File.join(runtime, "#{node[:name]}.json")
    File.write(path, JSON.generate(settings.select { |key, _| keys.include?(key) }), perm: 0600)
    config.vm.define node[:name] do |vm|
      vm.vm.hostname = node[:name]
      vm.vm.network 'private_network', ip: node[:ip]
      # Vagrant bootstrap management only, never a database/application forward.
      vm.vm.network 'forwarded_port', guest: 22, host: 2200 + index,
                    host_ip: '127.0.0.1', id: 'ssh', auto_correct: true
      if node[:role] == 'lb'
        vm.vm.network 'forwarded_port', guest: 80, host: 8080, host_ip: '127.0.0.1', auto_correct: false
      end
      vm.vm.provider 'virtualbox' do |vb|
        vb.memory = node[:memory]
        vb.cpus = 1
        vb.gui = false
      end
      vm.vm.provision 'shell', name: 'prepare-upload', run: 'always', privileged: false,
        inline: 'install -d -m 700 /home/vagrant/resultats-upload'
      {'inventory.json' => File.join(runtime, 'inventory.json'),
       'secrets.json' => path, 'provision.py' => 'scripts/provision.py',
       'service.py' => 'app/service.py'}.each do |destination, source|
        vm.vm.provision 'file', source: source,
          destination: "/home/vagrant/resultats-upload/#{destination}", run: 'always'
      end
      vm.vm.provision 'shell', name: 'configure', run: 'always',
        inline: "python3 /home/vagrant/resultats-upload/provision.py #{node[:name]}", sensitive: true
    end
  end
end
