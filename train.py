import torch
from tqdm import tqdm
from glob import glob
from data import NpzDataset
from model import UNet
import numpy as np
import argparse
import random
import os


def train(
        model, train_loader, device, criterion, optimizer, length,
        test_loader, not_earth, outdir
    ):

    train_losses = []
    test_losses = []

    for epoch in range(epochs):
        for data in tqdm(train_loader):
            # get the inputs; data is a list of [inputs, labels]
            inputs, labels = data['X'].to(device), data['y'].to(device)

            # zero the parameter gradients
            optimizer.zero_grad()

            # forward + backward + optimize
            outputs = model(inputs) # (batch_size, n_classes, img_cols, img_rows)

            outputs = outputs.reshape(length)
            labels = labels.reshape(length)

            # loss = criterion(outputs, labels)
            loss = criterion(outputs[not_earth], labels[not_earth])
            
            loss.backward()
            optimizer.step()

        # print statistics
        print(f'{(epoch + 1):3d} loss: {loss.item()}')
        train_losses.append(loss.item())

        eval_dir = f'{outdir}/{epoch}'
        try:
            os.makedirs(eval_dir)
        except FileExistsError:
            pass
        test_loss = evaluate(model, test_loader, device, criterion, length, not_earth, eval_dir)
        test_losses.append(test_loss)

    losses = {
        'train_losses': train_losses,
        'test_losses': test_losses
    }

    np.savez(f'{outdir}/losses.npz', **losses)

    return model


def evaluate(model, test_loader, device, criterion, length, not_earth, outdir):
    model.eval()
    preds = torch.tensor([], dtype=torch.float32).to(device)
    truth = torch.tensor([], dtype=torch.float32).to(device)

    with torch.no_grad():
        for i, data in tqdm(enumerate(test_loader)):
            inputs, labels = data['X'].to(device), data['y'].to(device)

            outputs = unet(inputs)

            results = {
                'outputs': outputs.detach().cpu().numpy().squeeze(),
                'labels': labels.detach().cpu().numpy().squeeze()
            }
            np.savez(f'{outdir}/{i}.npz', **results)

            # flat_outputs = outputs.reshape(length)
            # flat_labels = labels.reshape(length)
            flat_outputs = outputs.reshape(length)[not_earth]
            flat_labels = labels.reshape(length)[not_earth]

            preds = torch.cat((preds, flat_outputs))
            truth = torch.cat((truth, flat_labels))
    
    loss = criterion(preds, truth)

    print(f'Test loss: {loss.item()}')

    return loss.item()


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-i', '--indir', required=True, type=str)
    arg_parser.add_argument('-e', '--epochs', required=True, type=int)
    arg_parser.add_argument('-o', '--outdir', required=True, type=str)
    args = arg_parser.parse_args()

    try:
        os.makedirs(args.outdir)
    except FileExistsError:
        pass

    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    print('Device:', device)

    files = glob(f'{args.indir}/*.npz')

    features = ['Bx', 'By', 'Bz', 'Ex', 'Ey', 'Ez', 'rho']
    height_out = 344
    width_out = 620
    
    # features = ['Bx', 'By', 'Bz', 'absE', 'rho']
    # height_out = 216
    # width_out = 535
    
    num_classes = 1
    batch_size = 1
    epochs = args.epochs

    length = batch_size * num_classes * width_out * height_out

    first_file = np.load(files[0])
    not_earth = first_file['rho'] != 0
    not_earth = not_earth.reshape(length)

    random.shuffle(files)

    print(files)
    train_dataset = NpzDataset(files[:12], features)
    train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=batch_size)

    test_dataset = NpzDataset(files[12:15], features)
    test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=batch_size)

    unet = UNet(
        enc_chs=(len(features), 64, 128, 256),
        dec_chs=(256, 128, 64),
        num_class=1,
        retain_dim=True,
        out_sz=(height_out, width_out)
    ).to(device)
    print(unet)

    criterion = torch.nn.BCELoss()
    optimizer = torch.optim.Adam(unet.parameters(), lr=0.00001)

    unet = train(unet, train_loader, device, criterion, optimizer, length, test_loader, not_earth, args.outdir)
    print('Finished training!\n')

    print('Evaluating...')
    evaluate(unet, test_loader, device, criterion, length, not_earth, args.outdir)
